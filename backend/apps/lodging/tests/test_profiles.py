from io import BytesIO

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, PngImagePlugin

from apps.core.models import AuditEvent
from apps.lodging.models import Guest, Room


pytestmark = pytest.mark.django_db


def test_guest_identity_survives_contact_edits_and_shared_names(desk):
    details = {"full_name": "Synthetic Namesake", "phone": "0700000000"}
    a = desk("post", "guests", {**details, "email": "  EXAMPLE@Guest.invalid  ", "reference": "  "}, expect=201)
    assert a["reference"] and a["email"] == "example@guest.invalid" and a["phone"] == "0700000000"
    b = desk("post", "guests", details, expect=201)
    c = desk("post", "guests", details, expect=201)
    assert len({row["reference"] for row in (a, b, c)}) == 3
    desk("patch", f"guests/{b['id']}", {"email": "EXAMPLE@GUEST.INVALID"}, expect=(400, 409))
    desk("post", "guests", {**details, "reference": c["reference"]}, expect=(400, 409))
    assert Guest.objects.count() == 3
    assert desk("get", f"guests/{b['id']}")["email"] == ""
    edited = desk("patch", f"guests/{a['id']}", {"email": "", "phone": "0700000001"})
    assert edited["reference"] == a["reference"] and edited["phone"] == "0700000001"
    assert desk("patch", f"guests/{b['id']}", {"email": "example@guest.invalid"})["email"] == "example@guest.invalid"
    assert desk("get", "guests", {"search": a["reference"]})["count"] == 1
    events = AuditEvent.objects.filter(entity="lodging.guest")
    assert events.filter(object_id=a["id"]).count() == 2
    assert not any(details["full_name"] in s or "@" in s or "070000" in s for s in events.values_list("summary", flat=True))


def test_multipart_decodes_facilities_and_privately_reencodes_photo(desk, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    encoded = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("comment", "synthetic metadata to discard")
    Image.new("RGB", (12, 8), "green").save(encoded, "PNG", pnginfo=metadata)
    image = SimpleUploadedFile("client-filename.png", encoded.getvalue(), content_type="image/png")
    result = desk("post", "rooms", {"number": "009", "category": "Twin", "capacity": "2", "nightly_rate": "500.00",
                  "facilities": '["Desk", "Wi-Fi"]', "image": image}, form=True, expect=201)
    assert result["facilities"] == ["Desk", "Wi-Fi"] and result["is_active"] is True
    assert result["occupied"] is False and result["maintenance"] is False
    assert result["image"].startswith("/api/v1/media/rooms/") and result["image"].endswith(".jpg")
    assert "client-filename" not in result["image"]
    bed = Room.objects.get(pk=result["id"])
    with bed.image.open("rb") as stored, Image.open(stored) as decoded:
        assert decoded.format == "JPEG" and decoded.size == (12, 8) and "comment" not in decoded.info

    path = f"rooms/{bed.pk}"
    assert desk("patch", path, {"facilities": ["Desk", "Fan"]}, form=True)["facilities"] == ["Desk", "Fan"]
    for bad in ('["Wifi", 0]', '{"Desk": true}', '["broken"'):
        desk("patch", path, {"facilities": bad}, form=True, expect=400)
    desk("patch", path, {"facilities": ["Fan", None]}, expect=400)
    bad_image = SimpleUploadedFile("not-actually-jpeg.jpg", b"Not image content", content_type="image/jpeg")
    desk("patch", path, {"image": bad_image}, form=True, expect=400)
    desk("patch", path, {"cleanliness": "dirty"}, expect=400)
    after = desk("get", path)
    assert (after["image"], after["facilities"], after["cleanliness"]) == (result["image"], ["Desk", "Fan"], "inspected")


def test_guest_history_has_only_own_stays_and_permission_filtered_receipts(
    desk, staff_api, django_user_model, room, guest, book,
):
    # Distinct identity despite the same name; actual ledger entries in two folios.
    other = desk("post", "guests", {"full_name": guest["full_name"]}, expect=201)
    recorded = []
    for n, person in enumerate((guest, other)):
        stay = book([room()["id"]], person=person)
        desk("post", f"reservations/{stay['id']}/check_in")
        folio = desk("get", "invoices", {"reservation": stay["id"]})["results"][0]
        payment = desk("post", f"invoices/{folio['id']}/payments", {
            "amount": "120.55", "reference": f"SYNTHETIC-HISTORY-{n}", "method": "cash",
        }, expect=(200, 201))
        recorded.append((stay["id"], payment["id"], payment["receipt_number"]))

    desk_worker = django_user_model.objects.create_user(username="lodging-test-reception")
    desk_worker.groups.add(Group.objects.get(name="Receptionist"))
    reception = staff_api(desk_worker)
    for person, (stay_id, tender_id, receipt) in zip((guest, other), recorded):
        result = reception("get", f"guests/{person['id']}/history")
        assert [r["id"] for r in result["reservations"]] == [stay_id]
        assert result["reservations"][0]["checked_in_at"] and result["reservations"][0]["checked_out_at"] is None
        assert [(p["id"], p["receipt_number"], p["amount"]) for p in result["payments"]] == [(tender_id, receipt, "120.55")]
        assert not {"reference", "method", "received_by"}.intersection(result["payments"][0])

    directory_reader = django_user_model.objects.create_user(username="lodging-test-profiles-only")
    guest_view = Permission.objects.get(content_type__app_label="core", codename="guests_view")
    directory_reader.user_permissions.add(guest_view)
    staff_api(directory_reader)("get", f"guests/{guest['id']}/history", expect=403)
    # A canonical role is a ceiling, not a substitute for the Django grant.
    # Narrow this test's Receptionist group to exercise financial field omission.
    role = Group.objects.get(name="Receptionist")
    role.permissions.set([guest_view])
    directory_reader.groups.add(role)
    read_only = staff_api(django_user_model.objects.get(pk=directory_reader.pk))
    limited = read_only("get", f"guests/{guest['id']}/history")
    assert [r["id"] for r in limited["reservations"]] == [recorded[0][0]] and "payments" not in limited
    read_only("patch", f"guests/{guest['id']}", {"full_name": "Not permitted"}, expect=403)
    read_only("get", f"reservations/{recorded[0][0]}", expect=403)
    reception("post", "rooms", {"number": "UNAUTHORIZED"}, expect=403)
    assert not Room.objects.filter(number="UNAUTHORIZED").exists()
