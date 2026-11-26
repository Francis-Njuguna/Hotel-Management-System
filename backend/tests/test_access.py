"""QA-05, 06 and 12: check the HTTP surface, not the presence of UI controls."""

import re
from datetime import timedelta
from io import BytesIO
from secrets import token_urlsafe
from urllib.parse import urlsplit

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import SESSION_KEY
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.core.models import Notification
from apps.housekeeping.models import CleaningTask, MaintenanceRequest
from apps.lodging.models import Guest

from .support import action, as_user, expect, get, page, request


pytestmark = pytest.mark.django_db


def browser(ip):
    # Exercise the actual anonymous login view and session/CSRF middleware over one origin.
    return APIClient(enforce_csrf_checks=True, HTTP_ORIGIN="https://testserver", REMOTE_ADDR=ip)


def csrf(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies[django_settings.CSRF_COOKIE_NAME].value}


def test_qa06_csrf_and_bad_credentials_create_no_authenticated_session(employee):
    user = employee("Receptionist")
    password = token_urlsafe(24)
    user.set_password(password)
    user.save(update_fields=["password"])
    client = browser("192.0.2.60")
    good = {"username": user.username, "password": password}
    assert get(client, "auth/me") == {"user": None}

    # Correct credentials are deliberately used here: credentials validation alone cannot pass this test.
    expect(request(client, "post", "auth/login", good), 403)
    expect(request(client, "post", "auth/login", good, HTTP_X_CSRFTOKEN="x" * 32), 403)
    assert get(client, "auth/me") == {"user": None} and SESSION_KEY not in client.session

    known = expect(request(client, "post", "auth/login", {**good, "password": "qa-wrong"}, **csrf(client)), 400, 401, 403)
    unknown = request(client, "post", "auth/login", {"username": "qa-no-such-user", "password": "qa-wrong"}, **csrf(client))
    assert (unknown.status_code, unknown.json()) == (known.status_code, known.json())
    assert get(client, "auth/me") == {"user": None} and SESSION_KEY not in client.session

    signed_in = expect(request(client, "post", "auth/login", good, **csrf(client)), 200).json()["user"]
    assert signed_in["id"] == user.pk and signed_in["roles"] == ["Receptionist"]
    assert get(client, "auth/me")["user"]["id"] == user.pk
    expect(request(client, "post", "auth/logout", {}), 403)
    assert get(client, "auth/me")["user"]["id"] == user.pk
    expect(request(client, "post", "auth/logout", {}, **csrf(client)), 200, 204)
    assert get(client, "auth/me") == {"user": None}
    expect(request(client, "get", "guests"), 403)
    user.is_active = False
    user.save(update_fields=["is_active"])
    disabled = request(client, "post", "auth/login", good, **csrf(client))
    assert (disabled.status_code, disabled.json()) == (known.status_code, known.json())
    assert get(client, "auth/me") == {"user": None} and SESSION_KEY not in client.session


@pytest.mark.django_db(transaction=True)
def test_reset_has_same_public_result_for_known_and_unknown_account(employee, settings, mailoutbox):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = employee("Accountant")
    old_password = token_urlsafe(24)
    user.set_password(old_password)
    user.save(update_fields=["password"])
    client = browser("192.0.2.61")
    assert get(client, "auth/me") == {"user": None}

    unverified = expect(request(client, "post", "auth/reset", {"email": user.email}, **csrf(client)), 200, 202)
    public_result = (unverified.status_code, unverified.json())
    assert not mailoutbox, "An address on file is not yet a verified recovery channel."

    owner = browser("192.0.2.62")
    get(owner, "auth/me")
    credentials = {"username": user.username, "password": old_password}
    assert expect(request(owner, "post", "auth/login", credentials, **csrf(owner)), 200).json()["user"]["id"] == user.pk
    challenge_path = "auth/recovery-email"
    issued = expect(request(owner, "post", challenge_path, {}, **csrf(owner)), 200, 202)
    assert len(mailoutbox) == 1 and mailoutbox[0].to == [user.email]
    challenge = re.search(r"/verify-email/([^\s]+)", mailoutbox[0].body)
    assert challenge is not None, "Mailbox proof must come from the verification message."
    proof = {"token": challenge.group(1)}
    assert proof["token"].encode() not in issued.content, "The API response must not substitute for access to the mailbox."

    # Possession of the link is insufficient without the matching signed-in account.
    confirm_path = f"{challenge_path}/confirm"
    expect(request(client, "post", confirm_path, proof, **csrf(client)), 403)
    other = browser("192.0.2.63")
    coworker = employee("Accountant")
    other.force_login(coworker)
    assert get(other, "auth/me")["user"]["id"] == coworker.pk
    expect(request(other, "post", confirm_path, proof, **csrf(other)), 400, 403)
    pending = request(client, "post", "auth/reset", {"email": user.email}, **csrf(client))
    assert (pending.status_code, pending.json()) == public_result and len(mailoutbox) == 1
    expect(request(owner, "post", confirm_path, proof, **csrf(owner)), 200, 204)

    known = expect(request(client, "post", "auth/reset", {"email": user.email}, **csrf(client)), 200, 202)
    assert len(mailoutbox) == 2 and mailoutbox[1].to == [user.email]
    missing = request(client, "post", "auth/reset", {"email": "qa-absent@example.invalid"}, **csrf(client))
    assert public_result == (known.status_code, known.json()) == (missing.status_code, missing.json())
    assert len(mailoutbox) == 2, "An unknown address must not receive mail."
    assert SESSION_KEY not in client.session
    link = re.search(r"/reset/(?P<uid>[\w-]+)/(?P<token>[\w-]+)", mailoutbox[1].body)
    assert link is not None, "eligible synthetic staff must receive a usable reset link"
    new_password = token_urlsafe(24)
    confirm = {**link.groupdict(), "password": new_password}
    expect(request(client, "post", "auth/reset/confirm", confirm, **csrf(client)), 200, 204)
    expect(request(client, "post", "auth/reset/confirm", {**confirm, "password": token_urlsafe(24)}, **csrf(client)), 400, 403)
    expect(request(client, "post", "auth/login", {"username": user.username, "password": old_password}, **csrf(client)), 400, 401, 403)
    renewed = expect(request(client, "post", "auth/login", {"username": user.username, "password": new_password}, **csrf(client)), 200)
    assert renewed.json()["user"]["id"] == user.pk


def test_qa05_anonymous_and_roleless_requests_fail_closed(django_user_model):
    anonymous = APIClient()
    unassigned = as_user(django_user_model.objects.create_user(username="qa-unassigned"))
    for client in (anonymous, unassigned):
        expect(request(client, "get", "dashboard"), 403)
        expect(request(client, "get", "guests"), 403)
        expect(request(client, "post", "guests", {"full_name": "Denied QA Guest"}), 403)
    assert not Guest.objects.exists()


@pytest.mark.parametrize(("role", "allowed", "denied"), [
    ("Super Administrator", ("staff", "audit", "invoices"), ()),
    ("Hotel Manager", ("audit", "invoices", "rooms"), ("staff",)),
    ("Receptionist", ("guests", "reservations", "vehicles"), ("staff", "cleaning-tasks", "audit")),
    ("Housekeeping Staff", ("cleaning-tasks",), ("guests", "invoices", "orders", "vehicles")),
    ("Restaurant Staff", ("menu-items", "orders/stays"), ("guests", "reservations", "payments", "vehicles")),
    ("Accountant", ("payments", "invoices"), ("guests", "reservations", "vehicles", "staff")),
    ("Maintenance Staff", ("maintenance",), ("cleaning-tasks", "invoices", "vehicles", "staff")),
], ids=lambda x: x if isinstance(x, str) else None)
def test_qa05_canonical_role_grants(role, allowed, denied, admin_user, employee):
    user = admin_user if role == "Super Administrator" else employee(role)
    client = APIClient()
    client.force_login(user)  # Real Group/Permission and session lookup, not mocked capabilities.
    me = get(client, "auth/me")["user"]
    assert role in me["roles"] and "dashboard.view" in me["capabilities"]
    for stem in allowed:
        page(client, stem)
    for stem in denied:
        expect(request(client, "get", stem), 403)


def test_manager_cannot_grant_their_own_account_staff_administration(employee):
    manager = employee("Hotel Manager")
    expect(request(as_user(manager), "patch", f"staff/{manager.pk}", {"role": "Super Administrator"}), 403)
    manager.refresh_from_db()
    assert not manager.is_superuser and list(manager.groups.values_list("name", flat=True)) == ["Hotel Manager"]


def test_qa12_assigned_task_list_detail_dashboard_notification_and_mutation(employee, room, guest):
    alice, bob = employee("Housekeeping Staff"), employee("Housekeeping Staff")
    own = CleaningTask.objects.create(room=room(), assignee=alice, status="assigned", notes="QA own task")
    other = CleaningTask.objects.create(room=room(), assignee=bob, status="assigned", notes="QA unrelated task")
    own_note = Notification.objects.create(recipient=alice, title="QA own notification", message="For A")
    other_note = Notification.objects.create(recipient=bob, title="QA other notification", message="For B")
    client = as_user(alice)

    visible = page(client, "cleaning-tasks", {"page_size": 1})
    assert visible["count"] == 1 and visible["next"] is None
    assert [t["id"] for t in visible["results"]] == [own.pk]
    assert page(client, "cleaning-tasks", {"search": other.notes})["count"] == 0
    assert [t["id"] for t in page(client, "cleaning-tasks", {"search": own.notes})["results"]] == [own.pk]
    assert get(client, f"cleaning-tasks/{own.pk}")["room"] == own.room_id
    expect(request(client, "get", f"cleaning-tasks/{other.pk}"), 404)
    expect(request(client, "post", f"cleaning-tasks/{other.pk}/transition", {"status": "in_progress"}), 404)
    assert action(client, f"cleaning-tasks/{own.pk}/transition", {"status": "in_progress"})["status"] == "in_progress"
    other.refresh_from_db()
    assert other.status == "assigned" and other.assignee_id == bob.pk
    expect(request(client, "get", f"guests/{guest().pk}/history"), 403)
    expect(request(client, "get", "staff/assignees", {"role": "Housekeeping Staff"}), 403)

    dash = get(client, "dashboard")
    assert [t["id"] for t in dash["tasks"]] == [own.pk]
    assert not {"reservations", "orders"}.intersection(dash)
    assert not {"total_guests", "billed", "collected"}.intersection(dash["metrics"])
    assert own_note.pk in {n["id"] for n in dash["notifications"]}
    assert other_note.pk not in {n["id"] for n in dash["notifications"]}
    inbox = page(client, "notifications")
    assert other_note.pk not in {n["id"] for n in inbox["results"]}
    expect(request(client, "post", f"notifications/{other_note.pk}/read", {}), 404)
    assert action(client, f"notifications/{own_note.pk}/read")["read_at"]
    other_note.refresh_from_db()
    assert other_note.read_at is None


def test_qa12_maintenance_scope_includes_resolution(employee, room, today):
    alice, bob = employee("Maintenance Staff"), employee("Maintenance Staff")
    jobs = [MaintenanceRequest.objects.create(
        room=room(), assignee=user, description="QA work", status="open", blocking=False,
        start=today, end=today + timedelta(days=1),
    ) for user in (alice, bob)]
    own, other = jobs
    client = as_user(alice)
    result = page(client, "maintenance")
    assert result["count"] == 1 and [w["id"] for w in result["results"]] == [own.pk]
    assert get(client, f"maintenance/{own.pk}")["id"] == own.pk
    expect(request(client, "get", f"maintenance/{other.pk}"), 404)
    expect(request(client, "post", f"maintenance/{other.pk}/resolve", {}), 404)
    assert action(client, f"maintenance/{own.pk}/resolve")["status"] == "resolved"
    other.refresh_from_db()
    assert other.status == "open"


def test_room_image_download_uses_room_read_grant(admin_api, employee, room, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    bed = room()
    encoded = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(encoded, format="PNG")
    image = SimpleUploadedFile("qa-room.png", encoded.getvalue(), content_type="image/png")
    changed = expect(admin_api.patch(f"/api/v1/rooms/{bed.pk}/", {"image": image}, format="multipart", secure=True), 200)
    link = urlsplit(changed.json()["image"])
    target = link.path + (f"?{link.query}" if link.query else "")
    assert target.startswith("/api/v1/")
    authorized = expect(as_user(employee("Receptionist")).get(target, secure=True), 200)
    data = b"".join(authorized.streaming_content) if authorized.streaming else authorized.content
    assert authorized.closed  # The test client owns request finalization, including streamed responses.
    with Image.open(BytesIO(data)) as image:
        assert image.size == (8, 8)
    expect(as_user(employee("Housekeeping Staff")).get(target, secure=True), 403, 404)
    expect(APIClient().get(target, secure=True), 403)
