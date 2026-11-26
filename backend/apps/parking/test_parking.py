"""Synthetic parking cases. These exercise the migrated schema, not a mock store."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.core.models import AuditEvent
from apps.lodging.models import Guest
from tests.support import action, as_user, create, expect, get, page, patch, request

from . import services
from .models import Allocation, ParkingSpace, Vehicle


pytestmark = pytest.mark.django_db


@pytest.fixture
def receptionist(django_user_model):
    user = django_user_model.objects.create_user(username="qa-parking-desk")
    user.groups.add(Group.objects.get(name="Receptionist"))
    return user


@pytest.fixture
def desk(receptionist):
    return as_user(receptionist)


@pytest.fixture
def guest():
    return Guest.objects.create(full_name="Synthetic Parking Guest", reference="QA-PARKING-ONE")


@pytest.fixture
def pair(guest):
    return ParkingSpace.objects.create(code="QA-P01"), Vehicle.objects.create(guest=guest, plate="00QA-V1")


def ids(client, path, **params):
    return {row["id"] for row in page(client, path, params)["results"]}


def test_plate_registration_normalizes_before_uniqueness_and_preserves_guest(desk, guest, receptionist):
    other = Guest.objects.create(full_name=guest.full_name, reference="QA-PARKING-TWO")
    saved = create(desk, "vehicles", {"guest": guest.pk, "plate": " 00 qa\u00a0-\t31a "})
    assert (saved["guest"], saved["guest_name"], saved["plate"], saved["allocated"]) == (
        guest.pk, guest.full_name, "00QA-31A", False,
    )
    assert not {"email", "phone"}.intersection(saved)
    expect(request(desk, "post", "vehicles", {"guest": other.pk, "plate": "00Qa-3 1A"}), 409)
    assert list(Vehicle.objects.values_list("pk", "plate", "guest_id")) == [(saved["id"], "00QA-31A", guest.pk)]
    assert ids(desk, "vehicles", search="00 qA - 31a") == {saved["id"]}
    assert ids(desk, "vehicles", search=guest.reference) == {saved["id"]}
    assert not ids(desk, "vehicles", guest=other.pk)

    for data in (
        {"guest": guest.pk, "plate": " \t\u00a0"}, {"guest": guest.pk, "plate": "ß" * 17},
        {"guest": guest.pk, "plate": 12345}, {"plate": "QA-NEW"},
        {"guest": other.pk + 100, "plate": "QA-NEW"},
    ):
        expect(request(desk, "post", "vehicles", data), 400)
    event = AuditEvent.objects.get(entity="parking.vehicle")
    assert (event.actor_id, event.verb, event.object_id) == (receptionist.pk, "parking.vehicle_registered", saved["id"])
    assert all(private not in event.summary for private in (saved["plate"], guest.full_name, guest.reference))


def test_availability_and_filtered_history_come_from_unreleased_rows(desk, guest, pair):
    space, vehicle = pair
    free = create(desk, "parking-spaces", {"code": "QA-P02"})
    retired = create(desk, "parking-spaces", {"code": "QA-P03", "is_active": False})
    assert free["available"] and not retired["available"] and not retired["occupied"]
    payload = {"space": space.pk, "vehicle": vehicle.pk}
    first = create(desk, "parking-allocations", payload)
    assert (first["status"], first["ended_at"], first["guest"], first["guest_name"]) == (
        "active", None, guest.pk, guest.full_name,
    )
    assert (first["space"], first["space_code"], first["vehicle"], first["vehicle_plate"]) == (
        space.pk, space.code, vehicle.pk, vehicle.plate,
    )
    assert ids(desk, "parking-spaces", available="true") == {free["id"]}
    assert ids(desk, "parking-spaces", available="false") == {retired["id"], space.pk}
    assert ids(desk, "parking-spaces", search="qa-p0") == {retired["id"], free["id"], space.pk}
    assert get(desk, f"parking-spaces/{space.pk}")["occupied"] is True
    assert ids(desk, "vehicles", allocated="true") == {vehicle.pk}
    assert not ids(desk, "parking-allocations", status="released")

    target = f"parking-allocations/{first['id']}/release"
    released = action(desk, target)
    ended = Allocation.objects.get(pk=first["id"])
    assert released["status"] == "released" and ended.ended_at >= ended.started_at
    assert get(desk, f"parking-spaces/{space.pk}")["available"] is True
    assert get(desk, f"vehicles/{vehicle.pk}")["allocated"] is False
    second = create(desk, "parking-allocations", payload)  # Same pair is reusable without deleting history.
    assert second["id"] != first["id"]
    assert ids(desk, "parking-allocations", status="active", search="00q a - v1") == {second["id"]}
    assert ids(desk, "parking-allocations", status="released", space=space.pk, search=space.code) == {first["id"]}
    assert ids(desk, "parking-allocations", vehicle=vehicle.pk, guest=guest.pk) == {first["id"], second["id"]}
    assert not ids(desk, "parking-allocations", guest=guest.pk + 100)
    first_page = page(desk, "parking-allocations", {"page_size": 1})
    assert first_page["count"] == 2 and first_page["next"] and first_page["results"][0]["id"] == second["id"]
    expect(request(desk, "post", target, {}), 409)  # Stale double-click must not release the new occupant.
    assert Allocation.objects.get(pk=first["id"]).ended_at == ended.ended_at
    assert Allocation.objects.get(pk=second["id"]).ended_at is None
    assert AuditEvent.objects.filter(verb="parking.released").count() == 1
    assert AuditEvent.objects.filter(verb="parking.allocated").count() == 2
    expect(request(desk, "get", "parking-allocations", {"status": "wrong"}), 400)
    expect(request(desk, "get", "parking-spaces", {"available": "wrong"}), 400)


def test_occupied_space_cannot_be_deactivated_and_both_active_keys_conflict(desk, guest, pair):
    space, vehicle = pair
    spare = ParkingSpace.objects.create(code="QA-SPARE")
    other = Vehicle.objects.create(guest=guest, plate="QA-V2")
    current = create(desk, "parking-allocations", {"space": space.pk, "vehicle": vehicle.pk})
    for space_id, vehicle_id in ((space.pk, other.pk), (spare.pk, vehicle.pk)):
        expect(request(desk, "post", "parking-allocations", {"space": space_id, "vehicle": vehicle_id}), 409)
    url = f"parking-spaces/{space.pk}"
    expect(request(desk, "patch", url, {"is_active": False, "code": "QA-RENAME"}), 409)
    expect(request(desk, "patch", url, {"code": spare.code}), 409)
    assert get(desk, url)["is_active"] is True and get(desk, url)["code"] == space.code
    assert not AuditEvent.objects.filter(verb="parking.space_updated").exists()
    action(desk, f"parking-allocations/{current['id']}/release")
    assert patch(desk, url, {"is_active": False})["available"] is False
    expect(request(desk, "post", "parking-allocations", {"space": space.pk, "vehicle": other.pk}), 409)
    assert Allocation.objects.count() == 1 and AuditEvent.objects.filter(verb="parking.space_updated").count() == 1


def test_associations_and_workflow_timestamps_are_not_client_writable(desk, guest, pair):
    space, vehicle = pair
    payload = {"space": space.pk, "vehicle": vehicle.pk}
    for extra in ({"guest": guest.pk}, {"ended_at": None}, {"started_at": "2020-01-01T00:00:00Z"}, {"status": "released"}):
        expect(request(desk, "post", "parking-allocations", {**payload, **extra}), 400)
    for field in ("space", "vehicle"):
        expect(request(desk, "post", "parking-allocations", {**payload, field: 2**63 - 1}), 400)
    assert not Allocation.objects.exists()
    row = create(desk, "parking-allocations", payload)
    path = f"parking-allocations/{row['id']}"
    expect(request(desk, "post", f"{path}/release", {"ended_at": "2020-01-01T00:00:00Z"}), 400)
    expect(request(desk, "patch", path, {"ended_at": None}), 403, 405)
    expect(request(desk, "delete", path), 403, 405)
    expect(request(desk, "patch", f"vehicles/{vehicle.pk}", {"guest": guest.pk}), 403, 405)
    assert Allocation.objects.get().ended_at is None and not AuditEvent.objects.filter(verb="parking.released").exists()


def test_read_grant_is_not_manage_and_unrelated_roles_cannot_read_plates(django_user_model, pair):
    space, vehicle = pair
    row = Allocation.objects.create(space=space, vehicle=vehicle)
    read_grant = Permission.objects.get(content_type__app_label="core", codename="parking_view")
    # Reduce a real role's Django grants in this isolated test only. The role
    # ceiling permits parking; the narrowed grants permit only the read action.
    desk_role = Group.objects.get(name="Receptionist")
    desk_role.permissions.set([read_grant])
    reader = django_user_model.objects.create_user(username="qa-parking-view-only")
    reader.groups.add(desk_role)
    view = as_user(reader)
    accountant = django_user_model.objects.create_user(username="qa-parking-accountant")
    accountant.groups.add(Group.objects.get(name="Accountant"))
    accountant.user_permissions.add(read_grant)
    unassigned = django_user_model.objects.create_user(username="qa-no-operating-role")
    unassigned.user_permissions.add(read_grant)
    denied = [as_user(accountant), as_user(unassigned), APIClient()]
    for path in ("parking-spaces", "vehicles", "parking-allocations", f"parking-spaces/{space.pk}",
                 f"vehicles/{vehicle.pk}", f"parking-allocations/{row.pk}"):
        expect(request(view, "get", path), 200)
        for client in denied:
            response = expect(request(client, "get", path, {"search": vehicle.plate}), 403)
            assert vehicle.plate.encode() not in response.content
    for method, path, data in (
        ("post", "parking-spaces", {"code": "QA-NOT-ALLOWED"}),
        ("patch", f"parking-spaces/{space.pk}", {"is_active": False}),
        ("post", "vehicles", {"guest": vehicle.guest_id, "plate": "QA-NOT-ALLOWED"}),
        ("post", "parking-allocations", {"space": space.pk, "vehicle": vehicle.pk}),
        ("post", f"parking-allocations/{row.pk}/release", {}),
    ):
        expect(request(view, method, path, data), 403)
    assert Allocation.objects.get().ended_at is None and not AuditEvent.objects.filter(entity__startswith="parking.").exists()


def test_database_enforces_each_partial_key_and_allows_equal_time_release(pair, guest):
    space, vehicle = pair
    second_space = ParkingSpace.objects.create(code="QA-P02")
    second_vehicle = Vehicle.objects.create(guest=guest, plate="QA-V2")
    row = Allocation.objects.create(space=space, vehicle=vehicle)
    for bay, car, constraint in (
        (space, second_vehicle, "parking_one_active_per_space"),
        (second_space, vehicle, "parking_one_active_per_vehicle"),
    ):
        with pytest.raises(IntegrityError) as failure, transaction.atomic():
            Allocation.objects.create(space=bay, vehicle=car)
        assert failure.value.__cause__.diag.constraint_name == constraint
    with pytest.raises(IntegrityError) as failure, transaction.atomic():
        Allocation.objects.filter(pk=row.pk).update(ended_at=row.started_at - timedelta(seconds=1))
    assert failure.value.__cause__.diag.constraint_name == "parking_allocation_time_order"
    Allocation.objects.filter(pk=row.pk).update(ended_at=row.started_at)
    assert Allocation.objects.create(space=space, vehicle=vehicle).pk != row.pk


def test_database_rejects_noncanonical_plate_even_when_save_is_bypassed(pair):
    _, vehicle = pair
    for invalid in ("", "mixedCase", "QA V1", "QA\u00a0V1"):
        with pytest.raises(IntegrityError) as failure, transaction.atomic():
            Vehicle.objects.filter(pk=vehicle.pk).update(plate=invalid)
        assert failure.value.__cause__.diag.constraint_name == "parking_vehicle_plate_canonical"
    assert Vehicle.objects.get(pk=vehicle.pk).plate == "00QA-V1"


@pytest.mark.parametrize("command", ["allocate", "release"])
def test_audit_write_failure_rolls_back_allocation_change(command, pair, receptionist, monkeypatch):
    space, vehicle = pair
    if command == "release":
        current = Allocation.objects.create(space=space, vehicle=vehicle)

    def fail_audit(*args):
        raise IntegrityError("synthetic audit failure")

    monkeypatch.setattr(services, "record", fail_audit)
    with pytest.raises(IntegrityError, match="synthetic audit failure"):
        if command == "allocate":
            services.allocate(receptionist, space_id=space.pk, vehicle_id=vehicle.pk)
        else:
            services.release(receptionist, current)
    assert not Allocation.objects.filter(ended_at__isnull=False).exists()
    assert Allocation.objects.count() == (1 if command == "release" else 0)
    assert not AuditEvent.objects.filter(entity__startswith="parking.").exists()
