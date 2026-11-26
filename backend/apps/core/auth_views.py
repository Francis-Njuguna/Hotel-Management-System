import logging
import time
from functools import partial
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .access import CAPS, can
from .schema import DetailSchema, LoginInput, ResetConfirmInput, ResetInput, SessionSchema, TokenInput
from .models import StaffProfile

User = get_user_model()
logger = logging.getLogger(__name__)


def version_of(user):
    return StaffProfile.objects.filter(user=user).values_list('session_version',flat=True).first() or 0


class StaffResetTokens(PasswordResetTokenGenerator):
    def __init__(self, staff_version):
        super().__init__()
        self.staff_version = staff_version

    def _make_hash_value(self,user,timestamp):
        return f'{super()._make_hash_value(user,timestamp)}:{user.is_active}:{self.staff_version}'


def email_binding(user):
    return salted_hmac('hms-recovery-owner',f'{user.pk}:{user.email.strip().lower()}:{version_of(user)}:{user.password}').hexdigest()


def deliver(subject,body,to):
    try: send_mail(subject,body,settings.DEFAULT_FROM_EMAIL,[to],fail_silently=False)
    except (SMTPException,OSError):
        logger.error('Staff recovery email could not be delivered; check mail transport.')
        return False
    return True


def session_user(user):
    if not user.is_authenticated or not user.is_active:
        return None
    return {'id':user.pk, 'username':user.username, 'full_name':user.get_full_name() or user.username,
            'roles':list(user.groups.values_list('name',flat=True)) or (['Super Administrator'] if user.is_superuser else []),
            'capabilities':sorted(c for c in CAPS if can(user,c))}


class AddressThrottle(SimpleRateThrottle):
    scope = 'login'
    def get_cache_key(self,request,view):
        return self.cache_format % {'scope':self.scope, 'ident':self.get_ident(request)}


class ResetThrottle(AddressThrottle): scope = 'reset'


class VerifyThrottle(AddressThrottle): scope = 'verify_email'


@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    permission_classes = [AllowAny]
    @extend_schema(responses=SessionSchema)
    def get(self,request): return Response({'user':session_user(request.user)})


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AddressThrottle]
    @extend_schema(request=LoginInput,responses=SessionSchema)
    @transaction.atomic
    def post(self,request):
        payload=LoginInput(data=request.data); payload.is_valid(raise_exception=True)
        username,password=payload.validated_data['username'],payload.validated_data['password']
        User.objects.select_for_update().filter(username=username).only('id').first()
        user = authenticate(request,username=username,password=password)
        if not user or not user.is_active: return Response({'detail':'Invalid username or password.'},status=400)
        login(request,user)
        version = version_of(user)
        request.session.update({'started_at':int(time.time()),'last_seen':int(time.time()),'staff_version':version})
        return Response({'user':session_user(user)})


class LogoutView(APIView):
    @extend_schema(request=None,responses={204:None})
    def post(self,request):
        logout(request)
        return Response(status=204)


@method_decorator(csrf_protect, name='dispatch')
class ResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ResetThrottle]
    @extend_schema(request=ResetInput,responses=DetailSchema)
    def post(self,request):
        payload=ResetInput(data=request.data); payload.is_valid(raise_exception=True)
        email=payload.validated_data['email']
        with transaction.atomic():
            # The same user-row lock guards staff administration and reset redemption.
            # Read eligibility and version only after obtaining it. A unique index
            # protects each normalized nonblank address.
            user = User.objects.select_for_update().filter(email__iexact=email).first()
            if user and user.is_active and user.has_usable_password():
                version = StaffProfile.objects.filter(user=user, verified_email=email.lower()).values_list('session_version',flat=True).first()
                if version is not None:
                    uid = urlsafe_base64_encode(force_bytes(user.pk))
                    token = StaffResetTokens(version).make_token(user)
                    body = f'Open this one-time link to reset your staff password:\n{settings.PUBLIC_URL}/reset/{uid}/{token}'
                    transaction.on_commit(partial(deliver, 'Reset your Hotel A staff password', body, user.email))
        return Response({'detail':'If an eligible account exists, reset instructions have been sent.'})


@method_decorator(csrf_protect, name='dispatch')
class ConfirmResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ResetThrottle]
    @extend_schema(request=ResetConfirmInput,responses=DetailSchema)
    @transaction.atomic
    def post(self,request):
        payload=ResetConfirmInput(data=request.data); payload.is_valid(raise_exception=True)
        values=payload.validated_data
        try:
            uid = values['uid']
            if not isinstance(uid,str) or len(uid)>32: raise ValueError
            pk = int(urlsafe_base64_decode(uid))
            if not 0 < pk <= 2147483647: raise ValueError
            user = User.objects.select_for_update().get(pk=pk,is_active=True)
        except (ValueError,OverflowError,User.DoesNotExist):
            user = None
        token = values['token']
        if not user or not StaffResetTokens(version_of(user)).check_token(user,token):
            return Response({'detail':'Invalid or expired reset link.'},status=400)
        password = values['password']
        try: validate_password(password,user)
        except DjangoValidationError as err: raise serializers.ValidationError({'password':err.messages}) from err
        user.set_password(password); user.save(update_fields=['password'])
        return Response({'detail':'Password updated. Sign in again.'})


class VerifyAddressView(APIView):
    throttle_classes = [VerifyThrottle]
    @extend_schema(request=None,responses=DetailSchema)
    def post(self,request):
        user=request.user
        if not user.email: raise serializers.ValidationError({'email':'Ask your administrator to set a recovery address first.'})
        token=signing.TimestampSigner(salt='staff-verify-v1').sign(email_binding(user))
        sent=deliver('Verify your Hotel A recovery email',f'Sign in to your staff account to confirm this address:\n{settings.PUBLIC_URL}/verify-email/{token}',user.email)
        if not sent: return Response({'detail':'Email is unavailable. Ask your administrator to check mail delivery.'},status=503)
        return Response({'detail':'Check your staff mailbox for the verification link.'})


class ConfirmAddressView(APIView):
    throttle_classes=[VerifyThrottle]
    @extend_schema(request=TokenInput,responses=DetailSchema)
    @transaction.atomic
    def post(self,request):
        payload=TokenInput(data=request.data); payload.is_valid(raise_exception=True)
        user=User.objects.select_for_update().get(pk=request.user.pk)
        try: binding=signing.TimestampSigner(salt='staff-verify-v1').unsign(payload.validated_data['token'],max_age=settings.PASSWORD_RESET_TIMEOUT)
        except signing.BadSignature: binding=''
        if not user.email or not constant_time_compare(binding,email_binding(user)):
            raise serializers.ValidationError({'token':'This verification link is expired or belongs to a different account or address.'})
        StaffProfile.objects.update_or_create(user=user,defaults={'verified_email':user.email.strip().lower()})
        return Response({'detail':'Your recovery email is verified.'})
