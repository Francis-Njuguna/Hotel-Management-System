from datetime import date, datetime, time, timezone as dt_timezone
from itertools import count
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIClient


class StaffAPI:
    def __init__(self, user=None):
        self.client = APIClient()
        if user is not None:
            self.client.force_authenticate(user=user)

    def __call__(self, method, path, data=None, *, expect=200, form=False):
        url = f"/api/v1/{path.strip('/')}/"
        if method == "get":
            response = self.client.get(url, data=data, secure=True)
        else:
            response = getattr(self.client, method)(url, data if data is not None else {},
                                                    format="multipart" if form else "json", secure=True)
        assert response.status_code in (expect if isinstance(expect, tuple) else (expect,)), (
            method, path, response.status_code, response.content[:600]
        )
        return response.json()


@pytest.fixture
def staff_api():
    return StaffAPI


@pytest.fixture
def desk(admin_user):
    return StaffAPI(admin_user)


@pytest.fixture
def clock(monkeypatch):
    # Fixed **instant**, not a patched eligibility decision or simulated DB. Advance
    # the business day while exercising the real admission, posting and turnover.
    class HotelClock:
        day = date(2032, 6, 12)

        def now(self):
            local = datetime.combine(self.day, time(0, 15), tzinfo=ZoneInfo("Africa/Nairobi"))
            return local.astimezone(dt_timezone.utc)

    clock = HotelClock()
    monkeypatch.setattr(timezone, "now", clock.now)
    return clock


@pytest.fixture
def guest(desk):
    return desk("post", "guests", {"full_name": "Synthetic lodging guest"}, expect=201)


@pytest.fixture
def room(desk):
    seq = count(1)

    def register(rate="1250.00", **extra):
        return desk("post", "rooms", {"number": f"TEST-{next(seq):03d}", "category": "Double", "capacity": 2,
                                      "nightly_rate": rate, **extra}, expect=201)

    return register


@pytest.fixture
def book(desk, guest, clock):
    from datetime import timedelta

    def reserve(ids, *, arrival=None, nights=2, person=None, **extra):
        arrival = arrival or clock.day
        return desk("post", "reservations", {
            "guest": (person or guest)["id"], "arrival": arrival.isoformat(),
            "departure": (arrival + timedelta(days=nights)).isoformat(), "room_ids": ids, **extra,
        }, expect=201)

    return reserve
