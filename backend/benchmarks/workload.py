"""Explicit NFR-04 probe: from backend/, python -m pytest -qs benchmarks/workload.py.

Uses a fresh pytest-django database and its loopback live server, never a hotel URL.
Wall-clock results describe this synthetic, warm, single-client read workload only.
"""
from datetime import timedelta
from http.client import HTTPConnection
import json
from math import ceil
from statistics import median
from time import perf_counter
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.utils import timezone

from apps.lodging.models import Guest, Reservation, ReservationEvent, Room, RoomClaim


@pytest.mark.django_db(transaction=True)
def test_sample_manager_reads(live_server, client, django_user_model, settings):
    assert connection.vendor == 'postgresql' and connection.settings_dict['NAME'].startswith('test_')
    address = urlsplit(live_server.url)
    assert address.hostname in {'localhost', '127.0.0.1'} and address.port
    assert not Room.objects.exists() and not Guest.objects.exists()
    today = timezone.localdate()
    operator = django_user_model.objects.create_user(username='workload-fixture')
    operator.groups.add(Group.objects.get(name='Hotel Manager'))
    guests = Guest.objects.bulk_create([Guest(full_name=f'Workload guest {i}', reference=f'WL-G{i}') for i in range(600)])
    rooms = Room.objects.bulk_create([Room(number=f'WL-{i:02}',category='Double',capacity=2,nightly_rate='4000.00') for i in range(60)])
    stays = Reservation.objects.bulk_create([
        Reservation(guest=guests[i % 600], arrival=today + timedelta(days=i // 30),
                    departure=today + timedelta(days=i // 30 + 1), status='confirmed') for i in range(1200)])
    RoomClaim.objects.bulk_create([
        RoomClaim(reservation=r, room=rooms[2*(i % 30) + (i // 30) % 2],
                  start=r.arrival, end=r.departure, blocking=True, nightly_rate='4000.00') for i, r in enumerate(stays)])
    ReservationEvent.objects.bulk_create([ReservationEvent(reservation=r, actor=operator, status='confirmed') for r in stays])
    with connection.cursor() as cursor:
        cursor.execute('ANALYZE lodging_room, lodging_guest, lodging_reservation, lodging_roomclaim, lodging_reservationevent')

    # Establish one session before timing. Each GET still traverses the real
    # session, permission, ORM and serializer code over HTTP, with a fresh socket.
    client.force_login(operator)
    key = settings.SESSION_COOKIE_NAME
    headers = {'Host': address.netloc, 'Cookie': f'{key}={client.cookies[key].value}'}
    durations = {'dashboard': [], 'availability': []}
    print('Ready: 60 rooms, 600 guests and 1,200 stays. Measuring IPv4 loopback HTTP.', flush=True)
    for i in range(33):  # discard three warm-up pairs; rotate between both availability pages
        page = i % 2 + 1
        for label, route in (
            ('dashboard', 'dashboard/'),
            ('availability', f'rooms/availability/?arrival={today}&departure={today+timedelta(days=1)}&page={page}'),
        ):
            # Django's live fixture listens on an IPv4 socket. Avoid timing an
            # IPv6 connection refusal before every sample on dual-stack hosts.
            conn = HTTPConnection('127.0.0.1', address.port, timeout=30)
            try:
                start = perf_counter()
                conn.request('GET', '/api/v1/'+route, headers=headers)
                response = conn.getresponse()
                body = response.read()
                elapsed = (perf_counter()-start)*1000
            finally:
                conn.close()
            assert response.status == 200
            data = json.loads(body)
            if label == 'dashboard':
                m = data['metrics']
                assert (m['total_guests'],m['check_ins'],m['available_rooms'],m['reserved_rooms']) == (600,30,30,30)
            else:
                assert data['count'] == 30 and len(data['results']) == (25 if page==1 else 5)
            if i >= 3:
                durations[label].append(elapsed)
    print('Synthetic: 60 rooms; 600 guests; 1,200 confirmed stays/claims over 40 nights; no financial postings.')
    for label, times in durations.items():
        p95 = sorted(times)[ceil(.95*len(times))-1]
        print(f'{label}: {len(times)} loopback GETs; median {median(times):.1f} ms; nearest-rank p95 {p95:.1f} ms')
