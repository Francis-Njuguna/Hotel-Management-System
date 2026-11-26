from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .access import ROLES, can
from .api import Conflict, SecureViewSet
from .events import record
from .models import StaffProfile
from .schema import AssigneeSchema

User = get_user_model()


class StaffSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    department = serializers.CharField(max_length=80,required=False,allow_blank=True)
    role = serializers.ChoiceField(choices=list(ROLES), write_only=True)
    password = serializers.CharField(write_only=True,required=False,min_length=8,max_length=128,trim_whitespace=False)
    email = serializers.EmailField(required=True,allow_blank=False)

    class Meta:
        model = User
        fields = ['id','username','full_name','first_name','last_name','email','department','role','is_active','password']

    def get_full_name(self,obj) -> str: return obj.get_full_name() or obj.username

    def to_representation(self,instance):
        data = super().to_representation(instance)
        profile = getattr(instance,'staff_profile',None)
        data['department'] = profile.department if profile else ''
        data['role'] = 'Super Administrator' if instance.is_superuser else next((g.name for g in instance.groups.all() if g.name in ROLES), '')
        return data

    def validate_email(self,value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=getattr(self.instance,'pk',None)).exists():
            raise ValidationError('This staff email is already registered.')
        return value

    def validate(self,attrs):
        if self.instance is None and not attrs.get('password'): raise ValidationError({'password':'An initial password is required.'})
        if 'password' in attrs:
            try: validate_password(attrs['password'],self.instance or User(username=attrs.get('username',''),email=attrs.get('email','')))
            except DjangoValidationError as err: raise ValidationError({'password':err.messages}) from err
        return attrs

    @transaction.atomic
    def create(self,validated_data):
        role = validated_data.pop('role'); department = validated_data.pop('department','')
        try:
            with transaction.atomic(): user = User.objects.create_user(**validated_data)
        except IntegrityError as err:
            raise Conflict('This username or recovery email is already registered.') from err
        StaffProfile.objects.create(user=user,department=department)
        user.groups.set([Group.objects.get(name=role)])
        record(self.context['request'].user,'staff.created',user,'Staff account created')
        return user

    @transaction.atomic
    def update(self,instance,validated_data):
        actor = self.context['request'].user
        instance = User.objects.select_for_update().get(pk=instance.pk)
        if instance.is_superuser and not actor.is_superuser: raise PermissionDenied()
        if instance.pk == actor.pk and ('role' in validated_data or validated_data.get('is_active') is False):
            raise Conflict('Your own role and active status must be changed by another administrator.')
        role = validated_data.pop('role',None); department = validated_data.pop('department',None)
        password = validated_data.pop('password',None)
        if instance.is_superuser and role and role != 'Super Administrator': raise Conflict('Cannot change this administrator through the staff role selector.')
        address_changed = 'email' in validated_data and validated_data['email'] != instance.email
        activation_changed = 'is_active' in validated_data and validated_data['is_active'] != instance.is_active
        for key,value in validated_data.items(): setattr(instance,key,value)
        if password is not None: instance.set_password(password)
        try:
            with transaction.atomic(): instance.save()
        except IntegrityError as err:
            raise Conflict('This username or recovery email is already registered.') from err
        profile, _ = StaffProfile.objects.get_or_create(user=instance)
        if department is not None: profile.department = department
        if address_changed: profile.verified_email = ''
        if role: instance.groups.set([Group.objects.get(name=role)])
        if activation_changed or role or password or address_changed:
            profile.session_version += 1
        profile.save(update_fields=['department','session_version','verified_email'])
        changed=[label for flag,label in [(address_changed,'recovery address'),(role,'role'),(activation_changed,'activation'),(password,'password')] if flag]
        record(actor,'staff.updated',instance, 'Updated '+(', '.join(changed) or 'profile fields'))
        return instance


class StaffViewSet(mixins.ListModelMixin,mixins.RetrieveModelMixin,mixins.CreateModelMixin,mixins.UpdateModelMixin,SecureViewSet):
    serializer_class = StaffSerializer
    queryset = User.objects.select_related('staff_profile').prefetch_related('groups').order_by('username')
    search_fields = ['username','first_name','last_name','staff_profile__department']
    access = dict.fromkeys(['list','retrieve','create','update','partial_update'],'staff.manage')
    http_method_names = ['get','post','patch','head','options']

    @extend_schema(responses=AssigneeSchema(many=True),parameters=[OpenApiParameter('role',str,required=True)])
    @action(detail=False,methods=['get'], permission_classes=[IsAuthenticated])
    def assignees(self,request):
        allowed = {'Housekeeping Staff':'housekeeping.manage','Maintenance Staff':'maintenance.manage','Restaurant Staff':'restaurant.work'}
        role = request.query_params.get('role')
        if role not in allowed or not can(request.user,allowed[role]): raise PermissionDenied()
        self.search_fields = ['username','first_name','last_name']
        q = self.filter_queryset(self.get_queryset().filter(is_active=True,groups__name=role))
        page = self.paginate_queryset(q)
        return self.get_paginated_response([{'id':u.pk,'full_name':u.get_full_name() or u.username,'username':u.username} for u in page])
