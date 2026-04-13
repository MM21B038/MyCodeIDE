from pathlib import Path
import time

from fastapi.testclient import TestClient

from context_engine.api.main import app, engine


client = TestClient(app)


def wait_for_job(job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/index/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == "completed":
            return payload
        if payload["status"] == "failed":
            raise AssertionError(payload["error"])
        time.sleep(0.01)
    raise AssertionError("Index job did not complete in time.")


def test_homepage_serves_ui() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Context Engine" in response.text
    assert "Allow embedding model" in response.text


def test_upload_index_and_query_flow() -> None:
    response = client.post(
        "/index/upload",
        data={"root_name": "demo-project", "use_embeddings": "false"},
        files=[
            (
                "files",
                ("demo-project/auth.py", b"def login_user(email, password):\n    return email\n", "text/plain"),
            ),
            (
                "files",
                ("demo-project/routes.py", b"from auth import login_user\n", "text/plain"),
            ),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"queued", "running", "completed"}
    assert payload["embeddings_enabled"] is False

    completed = wait_for_job(payload["job_id"])
    assert completed["root_path"] == "demo-project"
    assert completed["files"] == 2

    query_response = client.post("/query", json={"query": "login user auth", "top_k": 5})

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert query_payload["indexed_root"] == "demo-project"
    assert query_payload["total_files"] == 2
    assert "login_user" in query_payload["context_pack"]
    assert len(query_payload["ranked_chunks"]) >= 1


def test_state_reports_current_index() -> None:
    engine.index_uploaded_codebase(
        Path("sample-root"),
        [(Path("main.py"), "def handle_request():\n    return True\n")],
    )

    response = client.get("/state")

    assert response.status_code == 200
    assert response.json()["indexed_root"] == "sample-root"
    assert response.json()["embeddings_enabled"] is False
