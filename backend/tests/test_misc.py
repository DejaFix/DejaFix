"""봉투·커서·시각 헬퍼, #5·#6 스텁, 라우트 목록."""

import re

import pytest

from dejafix_backend.envelope import decode_cursor, encode_cursor, ok
from dejafix_backend.timeutil import utc_now_iso


def test_ok_envelope():
    assert ok([1], next_cursor=None) == {"data": [1], "meta": {"next_cursor": None}}
    assert ok({"a": 1}) == {"data": {"a": 1}, "meta": {}}


def test_cursor_round_trip_with_korean_and_padding():
    fields = {"started_at": "2026-10-15T01:20:00Z", "id": 7, "memo": "한글"}
    cursor = encode_cursor(**fields)
    assert "=" not in cursor and "/" not in cursor and "+" not in cursor
    assert decode_cursor(cursor) == fields


@pytest.mark.parametrize("bad", ["***", "e30", "WzFd", "!!"])
def test_decode_cursor_rejects_garbage(bad):
    # "e30" = {} 는 올바른 JSON 이지만 필요한 필드가 없다 -> 호출 쪽(KeyError)에서 거른다
    if bad == "e30":
        assert decode_cursor(bad) == {}
        return
    with pytest.raises(ValueError):
        decode_cursor(bad)


def test_utc_now_iso_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now_iso())


# ---- #5·#6 (T32 전까지 스텁): 모양이 계약과 같은지만 확인한다


def test_summary_values_are_all_measured(client, oncall):
    body = client.get("/api/dashboard/summary", headers=oncall).json()
    data = body["data"]
    measured = [
        data["active_incidents"],
        data["high_incidents"],
        data["hosts"]["ok"],
        data["hosts"]["total"],
        data["hosts"]["unknown"],
        data["reports_today"],
        data["avg_analysis_sec"],
    ]
    for item in measured:
        assert {"value", "unit", "collected_at", "unknown"} <= set(item)
    unknown = data["avg_analysis_sec"]
    assert unknown["value"] is None and unknown["unknown"] is True
    assert unknown["unknown_reason"] == "NO_DATA"
    assert data["llm_usage_today"] is None
    assert body["meta"]["generated_at"].endswith("Z")


def test_problems_stub_filters_and_shape(client, oncall):
    body = client.get("/api/problems", headers=oncall).json()
    assert [p["eventid"] for p in body["data"]] == ["40211", "40219"]
    assert body["data"][1]["incident_id"] is None
    assert set(body["meta"]) == {"collected_at", "truncated"}
    high = client.get("/api/problems?severity_min=4", headers=oncall).json()["data"]
    assert [p["eventid"] for p in high] == ["40211"]
    host = client.get("/api/problems?hostid=10585", headers=oncall).json()["data"]
    assert [p["eventid"] for p in host] == ["40219"]
    assert client.get("/api/problems?severity_min=9", headers=oncall).status_code == 422


def test_required_routes_are_exposed(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        ("post", "/api/auth/login"),
        ("get", "/api/auth/me"),
        ("get", "/api/health"),
        ("get", "/api/dashboard/summary"),
        ("get", "/api/problems"),
        ("get", "/api/incidents"),
        ("get", "/api/incidents/{incident_id}"),
        ("post", "/api/chat"),
        ("get", "/healthz"),
    }
    exposed = {(m, p) for p, ops in paths.items() for m in ops}
    assert exposed == expected  # [선택]·[이후] API 를 미리 만들지 않았다


def test_cors_allows_only_configured_origin(client):
    allowed = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in other.headers


def test_app_refuses_to_start_without_jwt_secret(make_client):
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        make_client(JWT_SECRET="")
