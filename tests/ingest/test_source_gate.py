"""Tests for the MercadoLibre source gate with separated clients."""

from __future__ import annotations

import copy
import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from alquileres_uy.ingest.approval import APPROVAL_FILENAME
from alquileres_uy.ingest.client import MercadoLibreClient
from alquileres_uy.ingest.config import IngestionConfig
from alquileres_uy.ingest.errors import AuthenticationError
from alquileres_uy.ingest.models import SourceGateDecision
from alquileres_uy.ingest.source_gate import run_source_gate

from .conftest import FakeResponse, FakeSession, load_fixture


def _successful_search() -> FakeResponse:
    return FakeResponse(json_data=load_fixture("search_success.json"))


def _successful_multiget() -> FakeResponse:
    return FakeResponse(json_data=load_fixture("item_multiget_success.json"))


def _description() -> FakeResponse:
    return FakeResponse(json_data=load_fixture("description_success.json"))


def _site_categories() -> FakeResponse:
    return FakeResponse(
        json_data=[
            {"id": "MLU1743", "name": "Apartamentos"},
            {"id": "MLU1466", "name": "Casas"},
            {"id": "MLU9999", "name": "Otro"},
        ]
    )


def _config(tmp_path: Path, token: str | None = None) -> IngestionConfig:
    return IngestionConfig(
        output_dir=tmp_path / "raw",
        database_path=tmp_path / "ingestion.sqlite",
        access_token=token,
        requests_per_second=1e9,
        max_attempts=2,
    )


def _real_client(session: FakeSession, config: IngestionConfig) -> MercadoLibreClient:
    counter = {"v": 0.0}

    def _clock() -> float:
        counter["v"] += 10.0
        return counter["v"]

    return MercadoLibreClient(
        config,
        session=session,
        sleep=lambda _s: None,
        clock=_clock,
        rng=random.Random(0),
    )


class _StubClient:
    """Handwritten stub with the endpoints the gate needs."""

    def __init__(
        self,
        search_handler: Callable[[str, dict[str, Any] | None], FakeResponse],
        items_response: FakeResponse | None = None,
        description_response: FakeResponse | Exception | None = None,
        site_categories_response: FakeResponse | Exception | None = None,
    ) -> None:
        self._search_handler = search_handler
        self._items_response = items_response
        self._description_response = description_response
        self._site_categories_response = site_categories_response
        self.search_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.description_calls: list[str] = []
        self.site_categories_calls: list[str] = []

    def search_items(self, site_id: str, params: dict[str, Any] | None = None) -> FakeResponse:
        self.search_calls.append((site_id, params))
        return self._search_handler(site_id, params)

    def get_items(self, item_ids):  # type: ignore[no-untyped-def]
        if self._items_response is None:
            raise AssertionError("no items response configured")
        return self._items_response

    def get_item_description(self, item_id: str) -> FakeResponse:
        self.description_calls.append(item_id)
        if isinstance(self._description_response, Exception):
            raise self._description_response
        if self._description_response is None:
            raise AssertionError("no description response configured")
        return self._description_response

    def get_site_categories(self, site_id: str) -> FakeResponse:
        self.site_categories_calls.append(site_id)
        if isinstance(self._site_categories_response, Exception):
            raise self._site_categories_response
        if self._site_categories_response is None:
            return _site_categories()
        return self._site_categories_response


def test_gate_approved_writes_approval_and_verified_categories(tmp_path: Path) -> None:
    anonymous = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=_successful_multiget(),
        description_response=_description(),
        site_categories_response=_site_categories(),
    )
    workdir = tmp_path / "gate"

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=workdir
    )

    assert report.decision is SourceGateDecision.APPROVED
    assert report.verified_category_ids == {"apartment": "MLU1743", "house": "MLU1466"}
    assert artifacts.approval is not None
    approval_body = json.loads(artifacts.approval.read_text(encoding="utf-8"))
    assert approval_body["decision"] == "APPROVED"
    assert approval_body["category_ids"] == report.verified_category_ids
    assert approval_body["source_gate_report_sha256"]
    assert approval_body["source_gate_report_path"] == "coverage.json"


def test_gate_stays_inconclusive_when_site_categories_cannot_be_verified(tmp_path: Path) -> None:
    anonymous = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=_successful_multiget(),
        description_response=_description(),
        site_categories_response=FakeResponse(
            json_data=[{"id": "MLU9999", "name": "Something else"}]
        ),
    )

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert artifacts.approval is None
    assert not (tmp_path / "gate" / APPROVAL_FILENAME).exists()


def test_gate_rejected_when_essential_coverage_low(tmp_path: Path) -> None:
    payload = load_fixture("item_multiget_success.json")
    stripped = copy.deepcopy(payload)
    for entry in stripped:
        entry["body"]["attributes"] = []
        entry["body"].pop("location", None)
    anonymous = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=FakeResponse(json_data=stripped),
        description_response=_description(),
        site_categories_response=_site_categories(),
    )

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert report.decision is SourceGateDecision.REJECTED
    assert artifacts.approval is None


def test_gate_uses_authenticated_client_only_after_anonymous_401(tmp_path: Path) -> None:
    anonymous_session = FakeSession(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    auth_session = FakeSession(
        [
            FakeResponse(status_code=200, json_data=load_fixture("search_success.json")),
            FakeResponse(status_code=200, json_data=load_fixture("item_multiget_success.json")),
            FakeResponse(status_code=200, json_data=_site_categories().json()),
        ]
        + [FakeResponse(status_code=200, json_data=load_fixture("description_success.json"))] * 20
    )

    anonymous = _real_client(anonymous_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="s3cret"))

    report, _ = run_source_gate(
        _config(tmp_path, token="s3cret"),
        anonymous,
        authenticated,
        tmp_path / "gate",
    )

    assert anonymous_session.calls[0]["headers"].get("Authorization") in (None, "")
    assert anonymous_session.calls[0]["headers"].get("Authorization") != "Bearer s3cret"
    assert auth_session.calls, "authenticated session must have been used after 401"
    assert auth_session.calls[0]["headers"]["Authorization"] == "Bearer s3cret"
    assert report.token_used is True
    assert report.decision is SourceGateDecision.APPROVED


def test_gate_uses_authenticated_client_after_anonymous_403(tmp_path: Path) -> None:
    anonymous_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession(
        [
            FakeResponse(status_code=200, json_data=load_fixture("search_success.json")),
            FakeResponse(status_code=200, json_data=load_fixture("item_multiget_success.json")),
            FakeResponse(status_code=200, json_data=_site_categories().json()),
        ]
        + [FakeResponse(status_code=200, json_data=load_fixture("description_success.json"))] * 20
    )

    anonymous = _real_client(anonymous_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="s3cret"))

    report, _ = run_source_gate(
        _config(tmp_path, token="s3cret"), anonymous, authenticated, tmp_path / "gate"
    )

    assert auth_session.calls[0]["headers"]["Authorization"] == "Bearer s3cret"
    assert report.token_used is True


def test_gate_does_not_use_auth_client_when_anonymous_search_is_200(tmp_path: Path) -> None:
    anonymous_session = FakeSession(
        [
            FakeResponse(status_code=200, json_data=load_fixture("search_success.json")),
            FakeResponse(status_code=200, json_data=load_fixture("item_multiget_success.json")),
            FakeResponse(status_code=200, json_data=_site_categories().json()),
        ]
        + [FakeResponse(status_code=200, json_data=load_fixture("description_success.json"))] * 20
    )
    auth_session = FakeSession([])  # would raise on any request

    anonymous = _real_client(anonymous_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="s3cret"))

    report, _ = run_source_gate(
        _config(tmp_path, token="s3cret"), anonymous, authenticated, tmp_path / "gate"
    )

    assert report.token_used is False
    assert auth_session.calls == []
    assert anonymous_session.calls[0]["headers"].get("Authorization") in (None, "")


def test_gate_stays_token_free_when_no_authenticated_client_provided(tmp_path: Path) -> None:
    def _search(site_id: str, params: dict[str, Any] | None) -> FakeResponse:
        raise AuthenticationError(401, "unauthorized", url="/sites/MLU/search")

    anonymous = _StubClient(search_handler=_search)

    report, artifacts = run_source_gate(
        _config(tmp_path, token=None),
        anonymous,
        authenticated_client=None,
        workdir=tmp_path / "gate",
    )

    assert report.token_used is False
    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert artifacts.approval is None
    assert any("no MELI_ACCESS_TOKEN" in note for note in report.notes)


def test_gate_never_writes_the_token_into_any_artifact(tmp_path: Path) -> None:
    anonymous_session = FakeSession(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    auth_session = FakeSession(
        [
            FakeResponse(status_code=200, json_data=load_fixture("search_success.json")),
            FakeResponse(status_code=200, json_data=load_fixture("item_multiget_success.json")),
            FakeResponse(status_code=200, json_data=_site_categories().json()),
        ]
        + [FakeResponse(status_code=200, json_data=load_fixture("description_success.json"))] * 20
    )
    token = "very-secret-token-value"
    anonymous = _real_client(anonymous_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token=token))

    _, artifacts = run_source_gate(
        _config(tmp_path, token=token), anonymous, authenticated, tmp_path / "gate"
    )

    for artifact_path in (
        artifacts.coverage,
        artifacts.approval,
        artifacts.search_no_auth,
        artifacts.search_with_auth,
        artifacts.items_batch,
        artifacts.site_categories,
    ):
        if artifact_path is None:
            continue
        assert token not in artifact_path.read_text(
            encoding="utf-8"
        ), f"token leaked into {artifact_path}"


def test_gate_inconclusive_when_search_lacks_results(tmp_path: Path) -> None:
    empty = {
        "site_id": "MLU",
        "paging": {"total": 0, "offset": 0, "limit": 20},
        "results": [],
        "available_filters": [],
    }
    anonymous = _StubClient(
        search_handler=lambda site_id, params: FakeResponse(json_data=empty),
        items_response=None,
        description_response=None,
    )

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert report.sample_size == 0
    assert artifacts.approval is None


@pytest.mark.parametrize("missing_field", ["price"])
def test_gate_reports_partial_coverage(tmp_path: Path, missing_field: str) -> None:
    payload = load_fixture("item_multiget_success.json")
    weakened = copy.deepcopy(payload)
    for entry in weakened[:5]:
        entry["body"].pop(missing_field, None)
    anonymous = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=FakeResponse(json_data=weakened),
        description_response=_description(),
        site_categories_response=_site_categories(),
    )

    report, _ = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert report.essential_coverage[missing_field].present == 15
    assert report.decision is SourceGateDecision.REJECTED


# ---- probe artifacts: 401/403/network evidence -----------------------------


def _read_wrapper(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_anonymous_401_creates_wrapped_search_no_auth_artifact(tmp_path: Path) -> None:
    session = FakeSession(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    anonymous = _real_client(session, _config(tmp_path, token=None))

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert artifacts.search_no_auth is not None
    wrapper = _read_wrapper(artifacts.search_no_auth)
    assert wrapper["request"] == {
        "method": "GET",
        "endpoint": "/sites/MLU/search",
        "authenticated": False,
    }
    assert wrapper["response"]["status_code"] == 401
    assert wrapper["response"]["body"]["message"] == "invalid_token"
    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert artifacts.approval is None


def test_anonymous_403_creates_wrapped_search_no_auth_artifact(tmp_path: Path) -> None:
    session = FakeSession(
        [
            FakeResponse(
                status_code=403,
                json_data={"message": "forbidden", "error": "forbidden", "status": 403},
            )
        ]
    )
    anonymous = _real_client(session, _config(tmp_path, token=None))

    _, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    wrapper = _read_wrapper(artifacts.search_no_auth)
    assert wrapper["response"]["status_code"] == 403
    assert wrapper["response"]["body"]["error"] == "forbidden"
    assert "Authorization" not in wrapper["request"]
    assert "authorization" not in wrapper["response"]


def test_authenticated_error_creates_wrapped_search_with_auth_artifact(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession(
        [
            FakeResponse(
                status_code=403,
                json_data={"message": "still forbidden", "status": 403},
            )
        ]
    )
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="s3cret"))

    report, artifacts = run_source_gate(
        _config(tmp_path, token="s3cret"), anonymous, authenticated, tmp_path / "gate"
    )

    assert artifacts.search_with_auth is not None
    wrapper = _read_wrapper(artifacts.search_with_auth)
    assert wrapper["request"]["authenticated"] is True
    assert wrapper["response"]["status_code"] == 403
    assert wrapper["response"]["body"]["message"] == "still forbidden"
    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert report.token_used is True  # token was sent even though auth failed


def test_authenticated_401_creates_wrapped_search_with_auth_artifact(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="s3cret"))

    report, artifacts = run_source_gate(
        _config(tmp_path, token="s3cret"), anonymous, authenticated, tmp_path / "gate"
    )

    wrapper = _read_wrapper(artifacts.search_with_auth)
    assert wrapper["response"]["status_code"] == 401
    assert report.token_used is True


def test_network_error_creates_artifact_with_null_status(tmp_path: Path) -> None:
    from requests import Timeout

    session = FakeSession([Timeout("boom"), Timeout("boom"), Timeout("boom")])
    anonymous = _real_client(session, _config(tmp_path, token=None))

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert artifacts.search_no_auth is not None
    wrapper = _read_wrapper(artifacts.search_no_auth)
    assert wrapper["response"]["status_code"] is None
    assert wrapper["response"]["error_type"] == "MaxRetriesExceeded"
    assert "message" in wrapper["response"]
    assert report.decision is SourceGateDecision.INCONCLUSIVE


def test_search_with_auth_not_created_when_no_token_available(tmp_path: Path) -> None:
    session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    anonymous = _real_client(session, _config(tmp_path, token=None))

    _, artifacts = run_source_gate(
        _config(tmp_path, token=None),
        anonymous,
        authenticated_client=None,
        workdir=tmp_path / "gate",
    )

    assert artifacts.search_no_auth is not None
    assert artifacts.search_with_auth is None


def test_search_with_auth_not_created_when_anonymous_returns_200(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [
            FakeResponse(status_code=200, json_data=load_fixture("search_success.json")),
            FakeResponse(status_code=200, json_data=load_fixture("item_multiget_success.json")),
            FakeResponse(status_code=200, json_data=_site_categories().json()),
        ]
        + [FakeResponse(status_code=200, json_data=load_fixture("description_success.json"))] * 20
    )
    auth_session = FakeSession([])  # would explode on any call
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="s3cret"))

    report, artifacts = run_source_gate(
        _config(tmp_path, token="s3cret"), anonymous, authenticated, tmp_path / "gate"
    )

    assert artifacts.search_with_auth is None
    assert report.token_used is False
    assert auth_session.calls == []


def test_probe_artifacts_never_contain_authorization_header_or_token(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession(
        [
            FakeResponse(
                status_code=403,
                json_data={
                    "message": "still forbidden",
                    "status": 403,
                    # Attackers might echo request headers into responses;
                    # sanitizer must scrub these keys.
                    "authorization": "Bearer very-secret-token",
                    "token": "very-secret-token",
                },
            )
        ]
    )
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="very-secret-token"))

    _, artifacts = run_source_gate(
        _config(tmp_path, token="very-secret-token"),
        anonymous,
        authenticated,
        tmp_path / "gate",
    )

    text = artifacts.search_with_auth.read_text(encoding="utf-8")
    assert "very-secret-token" not in text
    assert "Bearer" not in text.split("very-secret-token")[0]  # nothing leaked


# ---- token_used semantics -----------------------------------------------


def test_token_used_false_when_anonymous_returns_200_even_with_token(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [
            FakeResponse(status_code=200, json_data=load_fixture("search_success.json")),
            FakeResponse(status_code=200, json_data=load_fixture("item_multiget_success.json")),
            FakeResponse(status_code=200, json_data=_site_categories().json()),
        ]
        + [FakeResponse(status_code=200, json_data=load_fixture("description_success.json"))] * 20
    )
    auth_session = FakeSession([])
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="tok"))

    report, _ = run_source_gate(
        _config(tmp_path, token="tok"), anonymous, authenticated, tmp_path / "gate"
    )

    assert report.token_used is False


def test_token_used_true_when_auth_call_returns_200(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    auth_session = FakeSession(
        [
            FakeResponse(status_code=200, json_data=load_fixture("search_success.json")),
            FakeResponse(status_code=200, json_data=load_fixture("item_multiget_success.json")),
            FakeResponse(status_code=200, json_data=_site_categories().json()),
        ]
        + [FakeResponse(status_code=200, json_data=load_fixture("description_success.json"))] * 20
    )
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="tok"))

    report, _ = run_source_gate(
        _config(tmp_path, token="tok"), anonymous, authenticated, tmp_path / "gate"
    )

    assert report.token_used is True


def test_token_used_true_when_auth_call_returns_403(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "still forbidden", "status": 403})]
    )
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="tok"))

    report, _ = run_source_gate(
        _config(tmp_path, token="tok"), anonymous, authenticated, tmp_path / "gate"
    )

    assert report.token_used is True


def test_token_used_true_when_auth_call_returns_401(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession(
        [FakeResponse(status_code=401, json_data=load_fixture("unauthorized.json"))]
    )
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="tok"))

    report, _ = run_source_gate(
        _config(tmp_path, token="tok"), anonymous, authenticated, tmp_path / "gate"
    )

    assert report.token_used is True


def test_token_used_true_when_auth_call_times_out(tmp_path: Path) -> None:
    from requests import Timeout

    anon_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession([Timeout("boom"), Timeout("boom"), Timeout("boom")])
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="tok"))

    report, _ = run_source_gate(
        _config(tmp_path, token="tok"), anonymous, authenticated, tmp_path / "gate"
    )

    assert report.token_used is True


def test_token_used_false_without_authenticated_client(tmp_path: Path) -> None:
    session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    anonymous = _real_client(session, _config(tmp_path, token=None))

    report, _ = run_source_gate(
        _config(tmp_path, token=None),
        anonymous,
        authenticated_client=None,
        workdir=tmp_path / "gate",
    )

    assert report.token_used is False


def test_coverage_reflects_token_used(tmp_path: Path) -> None:
    anon_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "forbidden", "status": 403})]
    )
    auth_session = FakeSession(
        [FakeResponse(status_code=403, json_data={"message": "still forbidden", "status": 403})]
    )
    anonymous = _real_client(anon_session, _config(tmp_path, token=None))
    authenticated = _real_client(auth_session, _config(tmp_path, token="tok"))

    _, artifacts = run_source_gate(
        _config(tmp_path, token="tok"), anonymous, authenticated, tmp_path / "gate"
    )

    coverage = json.loads(artifacts.coverage.read_text(encoding="utf-8"))
    assert coverage["token_used"] is True


# ---- required categories in the gate -----------------------------------


def test_gate_inconclusive_when_only_house_verified(tmp_path: Path) -> None:
    anonymous = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=_successful_multiget(),
        description_response=_description(),
        site_categories_response=FakeResponse(json_data=[{"id": "MLU1466", "name": "Casas"}]),
    )

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert artifacts.approval is None
    assert not (tmp_path / "gate" / APPROVAL_FILENAME).exists()
    assert "apartment" in " ".join(report.notes)


def test_gate_inconclusive_when_only_apartment_verified(tmp_path: Path) -> None:
    anonymous = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=_successful_multiget(),
        description_response=_description(),
        site_categories_response=FakeResponse(
            json_data=[{"id": "MLU1743", "name": "Apartamentos"}]
        ),
    )

    report, artifacts = run_source_gate(
        _config(tmp_path), anonymous, authenticated_client=None, workdir=tmp_path / "gate"
    )

    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert artifacts.approval is None
    assert "house" in " ".join(report.notes)
