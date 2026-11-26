"""Synthetic room-work acceptance cases; run against the integrated PostgreSQL test DB."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import OperationalError, connections, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import AuditEvent, Notification
from apps.lodging.models import Guest, Reservation, Room, RoomClaim

from . import services
from .models import CleaningTask, MaintenanceRequest


pytestmark = pytest.mark.django_db
DAY = timedelta(days=1)


def staff(username, role):
    user = get_user_model().objects.create_user(username=username, first_name="Synthetic", last_name=username)
    user.groups.add(Group.objects.get(name=role))
    return user


@pytest.fixture
def manager():
    return staff("hk-manager", "Hotel Manager")


@pytest.fixture
def cleaner():
    return staff("hk-cleaner", "Housekeeping Staff")


@pytest.fixture
def technician():
    return staff("hk-technician", "Maintenance Staff")


@pytest.fixture
def bed():
    return Room.objects.create(number="007", category="Double", nightly_rate="2100.00", capacity=2)


@pytest.fixture
def today():
    return timezone.localdate(timezone=timezone.get_default_timezone())


def http(actor, method, path, data=None, *, expect=200):
    client = APIClient()
    client.force_authenticate(user=actor)
    url = f"/api/v1/{path}/"
    if method == "get":
        response = client.get(url, data or {}, secure=True)
    else:
        response = client.post(url, data or {}, format="json", secure=True)
    assert response.status_code == expect, (path, response.status_code, response.content[:400])
    return response.json()


def transition(actor, task_id, status, *, expect=200, **fields):
    return http(actor, "post", f"cleaning-tasks/{task_id}/transition", {"status": status, **fields}, expect=expect)


def window(room, start, end, **extra):
    return {"room": room.pk, "description": "Synthetic repair", "start": start.isoformat(),
            "end": end.isoformat(), "blocking": True, **extra}


def test_turnover_with_other_work_requires_both_inspections(manager, cleaner, bed):
    desk = staff("hk-desk", "Receptionist")
    first = http(manager, "post", "cleaning-tasks", {"room": bed.pk, "assignee": cleaner.pk}, expect=201)
    assert (first["room_number"], first["assignee_name"], first["status"]) == ("007", cleaner.get_full_name(), "assigned")

    # Checkout creates its own pending turnover; an earlier task isn't proof it was done.
    second = services.turnover(bed, desk)
    assert (second.status, second.assignee_id) == ("pending", None)
    assert AuditEvent.objects.filter(actor=desk, entity=second._meta.label_lower, object_id=second.pk).exists()
    transition(manager, first["id"], "completed", expect=409)  # no skipping directly to complete
    transition(cleaner, first["id"], "in_progress")
    transition(cleaner, first["id"], "completed")
    transition(cleaner, first["id"], "inspected", expect=403)
    transition(manager, first["id"], "inspected")
    bed.refresh_from_db()
    assert bed.cleanliness == "dirty" and CleaningTask.objects.get(pk=second.pk).status == "pending"

    transition(manager, second.pk, "assigned", assignee=cleaner.pk)
    transition(cleaner, second.pk, "in_progress")
    transition(cleaner, second.pk, "completed")
    bed.refresh_from_db()
    assert bed.cleanliness == "dirty"
    transition(manager, second.pk, "inspected")
    bed.refresh_from_db()
    assert bed.cleanliness == "inspected"


@pytest.mark.parametrize("kind", ["cleaning-tasks", "maintenance"])
def test_filters_counts_detail_and_action_never_expand_worker_scope(kind, bed, manager, today):
    cleaning = kind == "cleaning-tasks"
    role = "Housekeeping Staff" if cleaning else "Maintenance Staff"
    me, other = staff("hk-one", role), staff("hk-two", role)
    base = {"room": bed.pk} if cleaning else window(bed, today, today + DAY, blocking=False)
    mine, theirs = [http(manager, "post", kind, {**base, "assignee": u.pk}, expect=201) for u in (me, other)]
    assert mine["assignee_name"] == me.get_full_name() and mine["room_number"] == bed.number
    queue = http(me, "get", kind, {"room": bed.pk, "status": mine["status"], "page_size": 1})
    assert queue["count"] == 1 and queue["next"] is None and queue["results"][0]["id"] == mine["id"]
    for filters in ({"assignee": other.pk}, {"search": other.username}):
        hidden = http(me, "get", kind, filters)
        assert hidden["count"] == 0 and hidden["results"] == []
    http(me, "get", f"{kind}/{theirs['id']}", expect=404)
    http(me, "post", kind, {**base, "assignee": me.pk}, expect=403)
    if cleaning:
        transition(me, theirs["id"], "in_progress", expect=404)
        transition(me, mine["id"], "in_progress", assignee=other.pk, expect=403)
        assert transition(me, mine["id"], "in_progress")["status"] == "in_progress"
        assert CleaningTask.objects.get(pk=theirs["id"]).status == "assigned"
    else:
        http(me, "post", f"{kind}/{theirs['id']}/resolve", expect=404)
        assert http(me, "post", f"{kind}/{mine['id']}/resolve")["status"] == "resolved"
        assert MaintenanceRequest.objects.get(pk=theirs["id"]).status == "open"


def test_rejected_dispatch_uses_current_active_role_and_no_client_state(manager, cleaner, technician, bed, today):
    # The manager has work permission but is not an eligible departmental assignee.
    for wrong in (manager, technician):
        http(manager, "post", "cleaning-tasks", {"room": bed.pk, "assignee": wrong.pk}, expect=400)
    http(manager, "post", "maintenance", window(bed, today, today + DAY, assignee=cleaner.pk), expect=400)
    get_user_model().objects.filter(pk=cleaner.pk).update(is_active=False)
    http(manager, "post", "cleaning-tasks", {"room": bed.pk, "assignee": cleaner.pk}, expect=400)
    http(manager, "post", "cleaning-tasks", {"room": bed.pk, "status": "inspected"}, expect=400)
    http(manager, "post", "maintenance", window(bed, today, today), expect=400)
    http(manager, "post", "maintenance", window(bed, today, today + DAY, status="resolved"), expect=400)
    bed.refresh_from_db()
    assert bed.cleanliness == "inspected"
    assert not CleaningTask.objects.exists() and not MaintenanceRequest.objects.exists() and not RoomClaim.objects.exists()
    assert not AuditEvent.objects.exists()


def test_resolution_releases_only_its_window_and_does_not_clean(manager, technician, cleaner, bed, today):
    current, future = [http(manager, "post", "maintenance", window(bed, start, start + DAY, assignee=technician.pk), expect=201)
                       for start in (today, today + DAY)]  # touching intervals, both commit
    task = http(manager, "post", "cleaning-tasks", {"room": bed.pk, "assignee": cleaner.pk}, expect=201)
    transition(cleaner, task["id"], "in_progress")
    transition(cleaner, task["id"], "completed")
    transition(manager, task["id"], "inspected", expect=409)
    assert CleaningTask.objects.get(pk=task["id"]).status == "completed"
    resolved = http(technician, "post", f"maintenance/{current['id']}/resolve")
    assert resolved["status"] == "resolved" and resolved["blocking"] is True  # retain original intent
    assert not RoomClaim.objects.get(maintenance_id=current["id"]).blocking
    assert RoomClaim.objects.get(maintenance_id=future["id"]).blocking
    bed.refresh_from_db()
    assert bed.cleanliness == "dirty"
    transition(manager, task["id"], "inspected")  # tomorrow's block does not block today's inspection
    bed.refresh_from_db()
    assert bed.cleanliness == "inspected"


def test_overdue_guest_blocks_current_closure_and_inspection_without_a_calendar_overlap(manager, cleaner, bed, today):
    arrival, departure = today - 3 * DAY, today - DAY
    guest = Guest.objects.create(full_name="Synthetic occupied-room guest", reference="HK-OVERSTAY")
    stay = Reservation.objects.create(guest=guest, arrival=arrival, departure=departure, status="checked_in",
                                      checked_in_at=timezone.now() - 3 * DAY)
    RoomClaim.objects.create(room=bed, reservation=stay, start=arrival, end=departure, blocking=True)
    http(manager, "post", "maintenance", window(bed, today, today + DAY), expect=409)
    assert not MaintenanceRequest.objects.exists() and RoomClaim.objects.count() == 1
    http(manager, "post", "maintenance", window(bed, today, today + DAY, blocking=False), expect=201)
    assert not RoomClaim.objects.filter(maintenance__isnull=False).exists()
    http(manager, "post", "maintenance", window(bed, today + DAY, today + 2 * DAY), expect=201)

    task = http(manager, "post", "cleaning-tasks", {"room": bed.pk, "assignee": cleaner.pk}, expect=201)
    transition(cleaner, task["id"], "in_progress")
    transition(cleaner, task["id"], "completed")
    transition(manager, task["id"], "inspected", expect=409)
    bed.refresh_from_db()
    assert bed.cleanliness == "dirty" and CleaningTask.objects.get(pk=task["id"]).status == "completed"
    assert Reservation.objects.get(pk=stay.pk).status == "checked_in"


def test_booking_calendar_exclusion_rolls_back_new_work_but_allows_adjacency(manager, bed, today):
    start, end = today + 3 * DAY, today + 5 * DAY
    guest = Guest.objects.create(full_name="Synthetic calendar guest", reference="HK-DATES")
    stay = Reservation.objects.create(guest=guest, arrival=start, departure=end, status="confirmed")
    sold = RoomClaim.objects.create(room=bed, reservation=stay, start=start, end=end, blocking=True)
    http(manager, "post", "maintenance", window(bed, end - DAY, end + DAY), expect=409)
    assert not MaintenanceRequest.objects.exists() and not AuditEvent.objects.exists()
    assert list(RoomClaim.objects.values_list("id", "blocking")) == [(sold.pk, True)]
    committed = http(manager, "post", "maintenance", window(bed, end, end + DAY), expect=201)
    claim = RoomClaim.objects.get(maintenance_id=committed["id"])
    assert (claim.start, claim.end, claim.room_id) == (end, end + DAY, bed.pk)
    assert claim.reservation_id is None and claim.blocking and claim.nightly_rate == Decimal("0.00")
    http(manager, "post", f"maintenance/{committed['id']}/resolve")
    sold.refresh_from_db()
    assert sold.blocking and sold.end == end


def test_failure_after_audit_rolls_back_task_room_claim_and_notification(manager, cleaner, technician, bed, today, monkeypatch):
    record = services.record

    def fail_after_audit(*args):
        record(*args)
        raise RuntimeError("Synthetic failure after audit")

    args = dict(room_id=bed.pk, start=today, end=today + DAY, description="Synthetic repair", blocking=True,
                assignee_id=technician.pk)
    with monkeypatch.context() as m:
        m.setattr(services, "record", fail_after_audit)
        with pytest.raises(RuntimeError, match="after audit"):
            services.create_cleaning_task(manager, room_id=bed.pk, assignee_id=cleaner.pk)
        with pytest.raises(RuntimeError, match="after audit"):
            services.open_maintenance(manager, **args)
    bed.refresh_from_db()
    assert bed.cleanliness == "inspected" and not CleaningTask.objects.exists()
    assert not MaintenanceRequest.objects.exists() and not RoomClaim.objects.exists()
    assert not AuditEvent.objects.exists() and not Notification.objects.exists()

    work = services.open_maintenance(manager, **args)
    monkeypatch.setattr(services, "record", fail_after_audit)
    with pytest.raises(RuntimeError, match="after audit"):
        services.resolve_maintenance(work, technician)
    work.refresh_from_db()
    assert work.status == "open" and RoomClaim.objects.get(maintenance=work).blocking
    assert AuditEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_assignment_holds_account_and_room_locks_until_commit(manager, cleaner, bed):
    task = services.create_cleaning_task(manager, room_id=bed.pk)

    def observe(room_id, user_id, task_id):
        # Separate connection. NO KEY UPDATE is compatible with FK-only key-share locks:
        # two lock_not_available results prove this command actually locked both parents.
        try:
            states = []
            for model, key in ((Room, room_id), (get_user_model(), user_id)):
                try:
                    with transaction.atomic():
                        model.objects.select_for_update(nowait=True, no_key=True).get(pk=key)
                except OperationalError as exc:
                    states.append(exc.__cause__.sqlstate)
                else:
                    states.append("unlocked")
            return states, CleaningTask.objects.get(pk=task_id).status
        finally:
            connections.close_all()

    with transaction.atomic():
        services.transition_cleaning_task(task, manager, status="assigned", assignee_id=cleaner.pk)
        with ThreadPoolExecutor(max_workers=1) as pool:
            locked, visible_state = pool.submit(observe, bed.pk, cleaner.pk, task.pk).result(timeout=10)
        assert locked == ["55P03", "55P03"] and visible_state == "pending"
    task.refresh_from_db()
    assert (task.status, task.assignee_id) == ("assigned", cleaner.pk)
