"""Complement B10's same-space race with independent PostgreSQL transactions."""

import pytest
from django.contrib.auth.models import Group

from apps.core.models import AuditEvent
from apps.lodging.models import Guest
from tests.overlap import overlap
from tests.support import expect

from .models import Allocation, ParkingSpace, Vehicle


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def operators(django_user_model):
    role = Group.objects.get(name="Receptionist")
    workers = [django_user_model.objects.create_user(username=f"qa-parking-{n}") for n in (1, 2)]
    for worker in workers:
        worker.groups.add(role)
    return workers


@pytest.mark.parametrize("first,rollback", [(0, False), (1, False), (0, True)])
def test_same_vehicle_different_spaces_commit_only_the_winner(settings, operators, first, rollback):
    guest = Guest.objects.create(full_name="Synthetic Parking Race Guest", reference="QA-P-RACE")
    vehicle = Vehicle.objects.create(guest=guest, plate="QA-RACE")
    spaces = [ParkingSpace.objects.create(code=code) for code in ("QA-A", "QA-B")]
    specs = [("parking-allocations", {"space": s.pk, "vehicle": vehicle.pk}) for s in spaces]
    a, b = overlap(settings, [operators[first], operators[1-first]], specs[first], specs[1 - first], rollback_first=rollback)
    expect(a, 201)  # The harness may subsequently roll back this tentative success.
    expect(b, 201 if rollback else 409)
    committed = Allocation.objects.get()
    assert committed.ended_at is None and committed.vehicle_id == vehicle.pk
    assert committed.space_id == spaces[1 - first if rollback else first].pk
    event = AuditEvent.objects.get(verb="parking.allocated")
    assert (event.object_id, event.actor_id) == (committed.pk, operators[1 - first if rollback else first].pk)


def test_racing_releases_preserve_the_first_stamp_and_one_event(settings, operators):
    guest = Guest.objects.create(full_name="Synthetic Parking Race Guest", reference="QA-P-RELEASE")
    vehicle = Vehicle.objects.create(guest=guest, plate="QA-RELEASE")
    row = Allocation.objects.create(space=ParkingSpace.objects.create(code="QA-R"), vehicle=vehicle)
    release = (f"parking-allocations/{row.pk}/release", {})
    a, b = overlap(settings, operators, release, release)
    assert expect(a, 200).json()["ended_at"]
    expect(b, 409)
    row.refresh_from_db()
    assert row.ended_at is not None and row.ended_at >= row.started_at
    assert AuditEvent.objects.get(verb="parking.released", object_id=row.pk).actor_id == operators[0].pk
