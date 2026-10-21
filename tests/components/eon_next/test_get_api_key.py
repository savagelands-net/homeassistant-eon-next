from __future__ import annotations

import builtins
import json
from collections.abc import Iterator
from typing import Any

import pytest

from tools import get_api_key


def _graphql_responses(*responses: dict[str, Any]):
    remaining: Iterator[dict[str, Any]] = iter(responses)

    def _graphql(id_token: str, query: str) -> dict[str, Any]:
        assert id_token == "browser-id-token"
        return next(remaining)

    return _graphql


def test_graphql_sends_browser_token_only_to_fixed_kraken_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        status = 200

        def read(self) -> bytes:
            return json.dumps({"data": {"viewer": {"liveSecretKey": None}}}).encode()

    class _Connection:
        def __init__(self, host: str, **kwargs: Any) -> None:
            captured["host"] = host
            captured["connection_kwargs"] = kwargs

        def request(self, method: str, path: str, **kwargs: Any) -> None:
            captured["method"] = method
            captured["path"] = path
            captured["request_kwargs"] = kwargs

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(get_api_key.http.client, "HTTPSConnection", _Connection)

    data = get_api_key.graphql("browser-id-token", get_api_key.LIVE_SECRET_KEY_QUERY)

    assert data == {"viewer": {"liveSecretKey": None}}
    assert captured["host"] == get_api_key.GRAPHQL_HOST
    assert captured["method"] == "POST"
    assert captured["path"] == get_api_key.GRAPHQL_PATH
    assert captured["request_kwargs"]["headers"]["Authorization"] == ("Bearer browser-id-token")
    assert captured["closed"] is True


def test_create_api_key_creates_key_when_none_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        get_api_key,
        "graphql",
        _graphql_responses(
            {"viewer": {"liveSecretKey": None}},
            {"regenerateSecretKey": {"key": "sk_live_new"}},
        ),
    )
    monkeypatch.setattr(
        builtins,
        "input",
        lambda _prompt: pytest.fail("New-key creation must not ask to replace a key"),
    )

    assert get_api_key.create_api_key("browser-id-token") == "sk_live_new"


def test_create_api_key_fails_closed_when_existing_key_status_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        get_api_key,
        "graphql",
        _graphql_responses({"viewer": {}}),
    )

    with pytest.raises(get_api_key.HelperError, match="whether an API key already exists"):
        get_api_key.create_api_key("browser-id-token")


def test_create_api_key_does_not_replace_existing_key_without_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[str] = []

    def _graphql(id_token: str, query: str) -> dict[str, Any]:
        queries.append(query)
        return {"viewer": {"liveSecretKey": "sk_live_****1234"}}

    monkeypatch.setattr(get_api_key, "graphql", _graphql)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "yes")

    assert get_api_key.create_api_key("browser-id-token") is None
    assert queries == [get_api_key.LIVE_SECRET_KEY_QUERY]


def test_create_api_key_replaces_existing_key_after_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        get_api_key,
        "graphql",
        _graphql_responses(
            {"viewer": {"liveSecretKey": "sk_live_****1234"}},
            {"regenerateSecretKey": {"key": "sk_live_replacement"}},
        ),
    )
    monkeypatch.setattr(builtins, "input", lambda _prompt: "REGENERATE")

    assert get_api_key.create_api_key("browser-id-token") == "sk_live_replacement"
