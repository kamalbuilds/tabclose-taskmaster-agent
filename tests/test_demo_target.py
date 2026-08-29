"""tests/test_demo_target.py — the demo_target service itself, using
FastAPI's TestClient (in-process, no real network socket, but exercises
the real app object). Covers per-region breaking, which is what makes a
live, on-camera single-region blip possible (break us-central1 only,
Observer A fails, Observer B stays healthy).
"""

from __future__ import annotations

import importlib
import os


def _fresh_app(tmp_path):
    state_path = tmp_path / "state.json"
    os.environ["DEMO_TARGET_STATE"] = str(state_path)
    import demo_target.app as app_module

    importlib.reload(app_module)
    return app_module


def test_health_ok_by_default(tmp_path):
    from fastapi.testclient import TestClient

    app_module = _fresh_app(tmp_path)
    client = TestClient(app_module.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_break_all_then_health_returns_503(tmp_path):
    from fastapi.testclient import TestClient

    app_module = _fresh_app(tmp_path)
    client = TestClient(app_module.app)
    client.post("/break", json={"region": "all"})
    resp = client.get("/health")
    assert resp.status_code == 503


def test_fix_restores_health(tmp_path):
    from fastapi.testclient import TestClient

    app_module = _fresh_app(tmp_path)
    client = TestClient(app_module.app)
    client.post("/break", json={"region": "all"})
    client.post("/fix", json={"region": "all"})
    resp = client.get("/health")
    assert resp.status_code == 200


def test_break_single_region_only_affects_that_region():
    """This is the live single-region-blip demo: break only us-central1,
    and europe-west1's probe (?region=europe-west1) must still see healthy.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DEMO_TARGET_STATE"] = f"{tmp}/state.json"
        import demo_target.app as app_module

        importlib.reload(app_module)
        from fastapi.testclient import TestClient

        client = TestClient(app_module.app)

        client.post("/break", json={"region": "us-central1"})

        resp_a = client.get("/health", params={"region": "us-central1"})
        assert resp_a.status_code == 503

        resp_b = client.get("/health", params={"region": "europe-west1"})
        assert resp_b.status_code == 200


def test_fix_one_region_leaves_other_broken():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DEMO_TARGET_STATE"] = f"{tmp}/state.json"
        import demo_target.app as app_module

        importlib.reload(app_module)
        from fastapi.testclient import TestClient

        client = TestClient(app_module.app)

        client.post("/break", json={"region": "us-central1"})
        client.post("/break", json={"region": "europe-west1"})
        client.post("/fix", json={"region": "us-central1"})

        resp_a = client.get("/health", params={"region": "us-central1"})
        assert resp_a.status_code == 200

        resp_b = client.get("/health", params={"region": "europe-west1"})
        assert resp_b.status_code == 503
