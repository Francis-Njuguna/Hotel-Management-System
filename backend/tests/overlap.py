"""Run two real APIClient requests, not two calls on TestCase's shared transaction.

The test-only middleware holds the first *application write* open until PostgreSQL
reports it is blocking the other request. It adds no business locks or writes and
doesn't replace an endpoint/service. Thus a double success cannot be hidden by a
lucky thread schedule; we can also model loss of the first transaction at commit.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Barrier, Event, local
from time import monotonic

from django.contrib.auth import get_user_model
from django.db import connections, transaction

from .support import as_user, request


_worker = local()
_LIMIT = 15


@dataclass
class Pair:
    rollback_first: bool
    start: Barrier = field(default_factory=lambda: Barrier(2, timeout=_LIMIT))
    first_wrote: Event = field(default_factory=Event)
    second_returned: Event = field(default_factory=Event)
    pids: dict = field(default_factory=dict)
    saw_block: bool = False


def hold_at_commit(get_response):
    def wrapped(http_request):
        participant = getattr(_worker, "participant", None)
        if participant is None:
            return get_response(http_request)
        pair, side = participant
        with transaction.atomic(), connections["default"].cursor() as cursor:
            # Bound a broken implementation as well as the coordination itself.
            cursor.execute("SET LOCAL lock_timeout TO '22s'")
            cursor.execute("SET LOCAL statement_timeout TO '30s'")
            cursor.execute("SELECT pg_backend_pid()")
            pair.pids[side] = cursor.fetchone()[0]
            pair.start.wait()  # Both inside the request stack, on live independent transactions.
            if side == 1:
                assert pair.first_wrote.wait(_LIMIT), "first request never reached its commit boundary"
                try:
                    return get_response(http_request)
                finally:
                    pair.second_returned.set()

            response = get_response(http_request)
            pair.first_wrote.set()
            if 200 <= response.status_code < 300:
                deadline = monotonic() + _LIMIT
                while monotonic() < deadline:
                    cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", (pair.pids[0], pair.pids[1]))
                    if cursor.fetchone()[0]:
                        pair.saw_block = True
                        break
                    if pair.second_returned.wait(0.02):
                        break  # It returned without blocking; surface this as missing evidence.
                if pair.rollback_first:
                    transaction.set_rollback(True)
            return response

    return wrapped


def overlap(settings, actors, first, second, *, rollback_first=False):
    """Each spec is (endpoint, JSON) for POST or (method, endpoint, JSON)."""
    db = connections["default"]
    assert db.vendor == "postgresql" and not db.in_atomic_block, "use django_db(transaction=True)"
    settings.MIDDLEWARE = [f"{__name__}.hold_at_commit", *settings.MIDDLEWARE]
    pair = Pair(rollback_first)
    actor_ids = tuple(user.pk for user in actors)
    assert len(actor_ids) == 2

    def invoke(side, spec):
        try:
            # Neither ORM objects with cached grants nor database handles cross threads.
            client = as_user(get_user_model().objects.get(pk=actor_ids[side]))
            _worker.participant = pair, side
            return request(client, *(spec if len(spec) == 3 else ("post", *spec)))
        except BaseException:
            pair.start.abort()
            raise
        finally:
            if side == 0:
                pair.first_wrote.set()
            else:
                pair.second_returned.set()
            _worker.participant = None
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke, side, spec) for side, spec in enumerate((first, second))]
        responses = [f.result(timeout=60) for f in futures]

    assert len(set(pair.pids.values())) == 2, f"requests did not use distinct backends: {pair.pids}"
    assert pair.saw_block, (
        "PostgreSQL did not observe actual lock contention before commit: "
        f"{[(r.status_code, r.content[:250]) for r in responses]}"
    )
    # All later state assertions use a newly connected observer, not a worker's snapshot.
    db.close()
    with db.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        assert cursor.fetchone()[0] not in pair.pids.values()
    return responses
