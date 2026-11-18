"""FRONTEND_DIST 정적 서빙(dejafix-app 합본 이미지): SPA 폴백이 API·healthz 를 가리지 않는다."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dejafix_backend.static import mount_frontend


def _dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    return dist


def _app(dist: str) -> TestClient:
    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    mount_frontend(app, dist)
    return TestClient(app)


def test_disabled_when_unset_or_missing(tmp_path):
    assert mount_frontend(FastAPI(), "") is False
    assert mount_frontend(FastAPI(), str(tmp_path / "none")) is False
    assert _app("").get("/").status_code == 404


def test_serves_index_assets_and_spa_fallback(tmp_path):
    c = _app(str(_dist(tmp_path)))
    assert c.get("/").text == "<html>spa</html>"
    assert c.get("/incidents/12").text == "<html>spa</html>"
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/favicon.svg").text == "<svg/>"


def test_api_and_healthz_not_shadowed(tmp_path):
    c = _app(str(_dist(tmp_path)))
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/api/ping").json() == {"pong": True}
    r = c.get("/api/nope")
    assert r.status_code == 404 and "spa" not in r.text
    assert c.get("/api").status_code == 404


def test_no_path_traversal(tmp_path):
    c = _app(str(_dist(tmp_path)))
    for p in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "secret" != c.get(p).text


def test_head_requests(tmp_path):
    c = _app(str(_dist(tmp_path)))
    assert c.head("/").status_code == 200
    assert c.head("/incidents/1").status_code == 200
    assert c.head("/api/nope").status_code == 404
    assert c.head("/healthz").status_code in (200, 405)
