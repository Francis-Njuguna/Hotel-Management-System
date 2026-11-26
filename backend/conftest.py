import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def isolate_request_throttle_budgets():
    # Tests are separate clients/scenarios, despite sharing the runner's loopback address.
    cache.clear()
