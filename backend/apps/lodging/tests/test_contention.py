"""Observe a real PostgreSQL lock wait on competing multi-room amendments."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from threading import Event
from time import monotonic

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections, transaction

from apps.core.api import Conflict
from apps.lodging import services
from apps.lodging.models import ReservationEvent, RoomClaim


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("rollback", [False, True], ids=["first-amendment-commits", "first-amendment-rolls-back"])
def test_contending_amendments_keep_the_losers_original_plan(rollback, admin_user, room, book, clock):
    assert connection.vendor == "postgresql" and not connection.in_atomic_block
    originals = [room()["id"], room()["id"]]
    shared, extra_a, extra_b = [room()["id"] for _ in range(3)]
    arrival = clock.day + timedelta(days=2)
    first, second = [book([pk], arrival=arrival)["id"] for pk in originals]
    user_id = admin_user.pk
    challenger_pid = Queue()

    def challenger():
        # Fetch a separate actor, connection and transaction in this thread.
        try:
            user = get_user_model().objects.get(pk=user_id)
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout TO '20s'")
                cursor.execute("SET LOCAL statement_timeout TO '25s'")
                cursor.execute("SELECT pg_backend_pid()")
                challenger_pid.put(cursor.fetchone()[0])
                try:
                    services.amend_reservation(second, user, room_ids=[extra_b, shared])
                except Conflict:
                    return False
                return True
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic(), connection.cursor() as observer:
            services.amend_reservation(first, admin_user, room_ids=[shared, extra_a])
            future = pool.submit(challenger)
            other_pid = challenger_pid.get(timeout=15)
            observer.execute("SELECT pg_backend_pid()")
            own_pid = observer.fetchone()[0]
            assert other_pid != own_pid
            deadline = monotonic() + 15
            pause = Event()
            while True:
                observer.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [own_pid, other_pid])
                if observer.fetchone()[0]:
                    break
                assert monotonic() < deadline and not future.done(), "The two commands did not actually contend."
                pause.wait(0.02)
            if rollback:
                transaction.set_rollback(True)
        assert future.result(timeout=30) is rollback

    # Check the committed result outside both workers' sessions (including events).
    connection.close()
    winners = {first: {shared, extra_a}, second: {originals[1]}} if not rollback else {
        first: {originals[0]}, second: {shared, extra_b},
    }
    for rid, expected in winners.items():
        assert set(RoomClaim.objects.filter(reservation_id=rid, blocking=True).values_list("room_id", flat=True)) == expected
        assert ReservationEvent.objects.filter(reservation_id=rid).count() == (2 if shared in expected else 1)
    assert RoomClaim.objects.filter(room_id=shared, blocking=True).count() == 1
