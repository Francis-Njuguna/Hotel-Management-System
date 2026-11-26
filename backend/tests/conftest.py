"""Only synthetic test data. Never seed grants or swap in an in-memory database."""

from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Group
from django.db import connections
from django.utils import timezone

from apps.billing.models import Invoice
from apps.core.models import StaffProfile
from apps.lodging.models import Guest, Room

from .support import OpenStay, action, as_user, booking, create


@pytest.fixture(scope="session", autouse=True)
def postgresql_only():
    # Fail (not skip) a misconfigured gate. No connection is opened by this check.
    if connections["default"].vendor != "postgresql":
        pytest.fail("B10 requires the migrated PostgreSQL test database; SQLite is not evidence.")


@pytest.fixture
def today():
    return timezone.localdate(timezone=ZoneInfo("Africa/Nairobi"))


@pytest.fixture
def admin_api(admin_user):
    assert admin_user.is_superuser
    return as_user(admin_user)


@pytest.fixture
def employee(django_user_model):
    ids = count(1)

    def make(role):
        key = f"qa-worker-{next(ids)}"
        user = django_user_model.objects.create_user(
            username=key, first_name="QA", last_name=key, email=f"{key}@example.invalid",
        )
        # Missing post_migrate data must fail; never manufacture a group or permission.
        user.groups.add(Group.objects.get(name=role))
        StaffProfile.objects.update_or_create(user=user, defaults={"department": "QA"})
        return user

    return make


@pytest.fixture
def guest():
    ids = count(1)

    def make():
        ref = f"QA-GUEST-{next(ids):03d}"
        return Guest.objects.create(
            reference=ref, full_name=f"Synthetic {ref}", email=f"{ref.lower()}@example.invalid",
            phone="",
        )

    return make


@pytest.fixture
def room():
    ids = count(101)

    def make(rate="2000.00"):
        return Room.objects.create(
            number=str(next(ids)), category="Double", nightly_rate=Decimal(rate), capacity=2,
            description="Synthetic QA room", facilities=[], cleanliness="inspected", is_active=True,
        )

    return make


@pytest.fixture
def open_stay(admin_api, guest, room, today):
    def make(rate="2000.00", nights=2):
        person, bed = guest(), room(rate)
        reservation = create(admin_api, "reservations", booking(person.pk, [bed.pk], today, nights=nights))
        rid = reservation["id"]
        assert action(admin_api, f"reservations/{rid}/check_in")["status"] == "checked_in"
        invoice = Invoice.objects.get(reservation_id=rid)
        return OpenStay(person.pk, bed.pk, rid, invoice.pk)

    return make
