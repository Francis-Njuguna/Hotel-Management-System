"""Account changes and recovery issuance share one PostgreSQL serialization point."""
import re
from secrets import token_urlsafe

import pytest
from rest_framework.test import APIClient

from apps.core.models import StaffProfile
from .overlap import overlap
from .support import as_user, expect, request


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('reset_first', [False, True])
def test_recovery_overlapping_disablement_cannot_survive_reactivation(settings, employee, mailoutbox, reset_first):
    owner, admin = employee('Receptionist'), employee('Super Administrator')
    old_password = token_urlsafe(24)
    owner.set_password(old_password)
    owner.save(update_fields=['password'])
    StaffProfile.objects.update_or_create(user=owner, defaults={'verified_email': owner.email})
    reset = ('auth/reset', {'email': owner.email})
    path = f'staff/{owner.pk}'
    disable = ('patch', path, {'is_active': False})
    actors, commands = ([owner, admin], [reset, disable]) if reset_first else ([admin, owner], [disable, reset])
    for response in overlap(settings, actors, *commands):
        expect(response, 200)
    expect(request(as_user(admin), 'patch', path, {'is_active': True}), 200)
    assert StaffProfile.objects.get(user=owner).session_version == 2
    assert len(mailoutbox) == int(reset_first)
    if reset_first:
        uid, token = re.search(r'/reset/([^/\s]+)/([^/\s]+)', mailoutbox[0].body).groups()
        expect(request(APIClient(), 'post', 'auth/reset/confirm', {'uid': uid, 'token': token, 'password': token_urlsafe(24)}), 400)
    owner.refresh_from_db()
    assert owner.is_active and owner.check_password(old_password)
