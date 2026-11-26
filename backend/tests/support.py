"""Small HTTP drivers; no application services, permissions, or finance calculators."""

from dataclasses import dataclass
from datetime import timedelta

from rest_framework.test import APIClient


def as_user(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def request(client, method, path, data=None, **headers):
    url = f"/api/v1/{path.strip('/')}/"
    if method == "get":
        return client.get(url, data=data, secure=True, **headers)
    return getattr(client, method)(url, data=data, format="json", secure=True, **headers)


def expect(response, *codes):
    assert response.status_code in codes, (
        f"{response.wsgi_request.method} {response.wsgi_request.path}: expected "
        f"{codes}, got {response.status_code}: {response.content[:500]!r}"
    )
    return response


def get(client, path, params=None):
    return expect(request(client, "get", path, params), 200).json()


def create(client, path, data):
    return expect(request(client, "post", path, data), 201).json()


def action(client, path, data=None):
    # Some commands create a related resource (e.g. a payment); others update one.
    return expect(request(client, "post", path, data or {}), 200, 201).json()


def patch(client, path, data):
    return expect(request(client, "patch", path, data), 200).json()


def page(client, path, params=None):
    result = get(client, path, params)
    assert {"count", "next", "previous", "results"} <= result.keys(), path
    assert isinstance(result["results"], list)
    return result


def booking(guest_id, room_ids, arrival, *, nights=2, **extra):
    return {
        "guest": guest_id,
        "room_ids": list(room_ids),
        "arrival": arrival.isoformat(),
        "departure": (arrival + timedelta(days=nights)).isoformat(),
        **extra,
    }


def food(client, name="QA lunch", price="850.25"):
    return create(client, "menu-items", {"name": name, "category": "QA Meals", "price": price, "available": True})


def money(invoice, total, paid, balance):
    # JSON contract is fixed-precision *strings*, not binary floats.
    assert (invoice["total"], invoice["paid"], invoice["balance"]) == (total, paid, balance)


@dataclass(frozen=True)
class OpenStay:
    guest_id: int
    room_id: int
    reservation_id: int
    invoice_id: int
