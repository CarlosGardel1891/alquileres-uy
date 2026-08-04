"""Tests for :class:`MercadoLibreClient`."""

from __future__ import annotations

import random

import pytest
import requests

from alquileres_uy.ingest.client import MercadoLibreClient
from alquileres_uy.ingest.config import IngestionConfig
from alquileres_uy.ingest.errors import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    MaxRetriesExceeded,
)

from .conftest import FakeResponse, load_fixture


def _config(**overrides: object) -> IngestionConfig:
    return IngestionConfig(
        max_attempts=3,
        requests_per_second=1000.0,  # effectively no rate limit in tests
        **overrides,  # type: ignore[arg-type]
    )


def _client(session, sleep_fn, config=None) -> MercadoLibreClient:
    counter = {"value": 0.0}

    def _advancing_clock() -> float:
        counter["value"] += 10.0
        return counter["value"]

    return MercadoLibreClient(
        config or _config(),
        session=session,
        sleep=sleep_fn,
        clock=_advancing_clock,
        rng=random.Random(0),
    )


def test_search_success_returns_response(make_session, sleep_recorder):
    payload = load_fixture("search_success.json")
    session = make_session([FakeResponse(status_code=200, json_data=payload)])
    _, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    response = client.search_items("MLU", params={"q": "alquiler"})

    assert response.status_code == 200
    assert response.json()["paging"]["total"] == 3200
    assert session.calls[0]["url"].endswith("/sites/MLU/search")


def test_401_without_token_raises_authentication_error(make_session, sleep_recorder):
    session = make_session(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    _, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    with pytest.raises(AuthenticationError) as info:
        client.search_items("MLU")

    assert info.value.status_code == 401


def test_403_is_not_retried(make_session, sleep_recorder):
    session = make_session([FakeResponse(status_code=403, json_data={"message": "forbidden"})])
    recorded, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    with pytest.raises(AuthorizationError):
        client.search_items("MLU")

    assert len(session.calls) == 1
    assert recorded == []


def test_400_is_not_retried(make_session, sleep_recorder):
    session = make_session([FakeResponse(status_code=400, json_data={"message": "bad request"})])
    recorded, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    with pytest.raises(BadRequestError):
        client.search_items("MLU")

    assert len(session.calls) == 1
    assert recorded == []


def test_429_with_retry_after_waits_then_succeeds(make_session, sleep_recorder):
    payload = load_fixture("search_success.json")
    session = make_session(
        [
            FakeResponse(
                status_code=429,
                json_data=load_fixture("rate_limited.json"),
                headers={"Retry-After": "1.5"},
            ),
            FakeResponse(status_code=200, json_data=payload),
        ]
    )
    recorded, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    response = client.search_items("MLU")

    assert response.status_code == 200
    assert recorded == [1.5]
    assert len(session.calls) == 2


def test_timeout_is_retried_and_eventually_gives_up(make_session, sleep_recorder):
    session = make_session(
        [
            requests.Timeout("boom"),
            requests.Timeout("boom"),
            requests.Timeout("boom"),
        ]
    )
    recorded, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    with pytest.raises(MaxRetriesExceeded):
        client.search_items("MLU")

    assert len(session.calls) == 3
    assert len(recorded) == 2  # slept between attempts, not after the last


def test_retry_with_token_after_401_uses_authorization_header(make_session, sleep_recorder):
    payload = load_fixture("search_success.json")
    unauth_session = make_session(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    _, sleep_fn = sleep_recorder
    anon_client = _client(unauth_session, sleep_fn)
    with pytest.raises(AuthenticationError):
        anon_client.search_items("MLU")

    auth_session = make_session([FakeResponse(status_code=200, json_data=payload)])
    auth_client = _client(
        auth_session,
        sleep_fn,
        config=_config(access_token="secret-token"),
    )
    auth_client.search_items("MLU")

    sent_headers = auth_session.calls[0]["headers"]
    assert sent_headers is not None
    assert sent_headers.get("Authorization") == "Bearer secret-token"


def test_multiget_batch_over_twenty_raises(make_session, sleep_recorder):
    session = make_session([])
    _, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    with pytest.raises(ValueError):
        client.get_items([f"MLU{i:06d}" for i in range(21)])


def test_multiget_success(make_session, sleep_recorder):
    payload = load_fixture("item_multiget_success.json")
    session = make_session([FakeResponse(status_code=200, json_data=payload)])
    _, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    response = client.get_items([entry["body"]["id"] for entry in payload])

    assert response.status_code == 200
    assert len(response.json()) == 20


def test_multiget_partial_failure_is_returned_intact(make_session, sleep_recorder):
    payload = load_fixture("item_multiget_partial_failure.json")
    session = make_session([FakeResponse(status_code=200, json_data=payload)])
    _, sleep_fn = sleep_recorder
    client = _client(session, sleep_fn)

    response = client.get_items(["MLU100001"])
    body = response.json()

    codes = [entry["code"] for entry in body]
    assert codes.count(200) == 18
    assert codes.count(404) == 2
