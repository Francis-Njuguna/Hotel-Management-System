import re
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient
from .models import StaffProfile

User=get_user_model()
pytestmark=pytest.mark.django_db


def account(name,role):
    user=User.objects.create_user(username=name,password='Example-Only-Staff-442!',email=f'{name}@example.invalid')
    user.groups.add(Group.objects.get(name=role)); return user


def test_cookie_login_requires_csrf_and_post_logout_revokes_session():
    account('desk-a','Receptionist')
    web=APIClient(enforce_csrf_checks=True)
    data={'username':'desk-a','password':'Example-Only-Staff-442!'}
    assert web.post('/api/v1/auth/login/',data,format='json').status_code==403
    assert web.get('/api/v1/auth/me/').json()['user'] is None
    assert web.post('/api/v1/auth/login/',data,format='json',HTTP_X_CSRFTOKEN=web.cookies['csrftoken'].value).status_code==200
    original=web.cookies['sessionid'].value
    assert web.post('/api/v1/auth/logout/',{}).status_code==403
    assert web.post('/api/v1/auth/logout/',{},HTTP_X_CSRFTOKEN=web.cookies['csrftoken'].value).status_code==204
    web.cookies['sessionid']=original
    assert web.get('/api/v1/auth/me/').json()['user'] is None


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
@pytest.mark.django_db(transaction=True)
def test_reset_reaches_verified_address_and_link_cannot_be_reused():
    u=account('cash-a','Accountant'); web=APIClient()
    assert web.post('/api/v1/auth/reset/',{'email':u.email},format='json').status_code==200
    assert len(mail.outbox)==0
    owner=APIClient(); owner.force_login(u)
    assert owner.post('/api/v1/auth/recovery-email/',{}).status_code==200
    token=re.search(r'/verify-email/([^\s]+)',mail.outbox.pop().body)[1]
    other=APIClient(); other.force_login(account('another','Receptionist'))
    assert other.post('/api/v1/auth/recovery-email/confirm/',{'token':token}).status_code==400
    assert owner.post('/api/v1/auth/recovery-email/confirm/',{'token':token}).status_code==200
    known=web.post('/api/v1/auth/reset/',{'email':u.email},format='json')
    unknown=web.post('/api/v1/auth/reset/',{'email':'absent@example.invalid'},format='json')
    assert known.status_code==unknown.status_code==200 and known.json()==unknown.json()
    assert len(mail.outbox)==1 and mail.outbox[0].to==[u.email]
    m=re.search(r'/reset/([^/\s]+)/([^/\s]+)',mail.outbox[0].body)
    post={'uid':m[1],'token':m[2],'password':'Changed-Local-Staff-932!'}
    assert web.post('/api/v1/auth/reset/confirm/',post,format='json').status_code==200
    assert web.post('/api/v1/auth/reset/confirm/',post,format='json').status_code==400
    u.refresh_from_db(); assert u.check_password(post['password'])


def test_admin_deactivation_removes_stored_session_even_after_reactivation():
    admin=account('admin-a','Super Administrator'); desk=account('desk-b','Receptionist')
    a=APIClient(); a.force_authenticate(admin)
    w=APIClient(); w.force_login(desk)
    url=f'/api/v1/staff/{desk.pk}/'
    assert a.patch(url,{'is_active':False},format='json').status_code==200
    assert a.patch(url,{'is_active':True},format='json').status_code==200
    assert w.get('/api/v1/auth/me/').json()['user'] is None


def test_app_admin_cannot_grant_django_flags_or_deactivate_self():
    admin=account('admin-b','Super Administrator'); a=APIClient(); a.force_authenticate(admin)
    assert a.patch(f'/api/v1/staff/{admin.id}/',{'is_active':False},format='json').status_code==409
    admin.refresh_from_db(); assert admin.is_active and not admin.is_superuser


def test_disable_reactivate_invalidates_password_recovery_awaiting_delivery(django_capture_on_commit_callbacks, mailoutbox):
    u=account('nightdesk','Receptionist'); StaffProfile.objects.create(user=u,verified_email=u.email)
    anon=APIClient()
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert anon.post('/api/v1/auth/reset/',{'email':u.email},format='json').status_code==200
    assert len(callbacks)==1 and not mailoutbox
    admin=APIClient(); admin.force_authenticate(account('leader','Super Administrator'))
    assert admin.patch(f'/api/v1/staff/{u.id}/',{'is_active':False}).status_code==200
    assert StaffProfile.objects.get(user=u).session_version==1
    assert admin.patch(f'/api/v1/staff/{u.id}/',{'is_active':True}).status_code==200
    assert StaffProfile.objects.get(user=u).session_version==2
    callbacks[0]()  # Delivery after both administrative changes still carries the original version.
    assert len(mailoutbox)==1
    link=re.search(r'/reset/([^/\s]+)/([^/\s]+)',mailoutbox[0].body)
    denied=anon.post('/api/v1/auth/reset/confirm/',{'uid':link[1],'token':link[2],'password':'Replacement-Example-489!'},format='json')
    assert denied.status_code==400
    u.refresh_from_db(); assert u.check_password('Example-Only-Staff-442!')
