import pymupdf
import pytest
from fastapi.testclient import TestClient

from reps_api import arena
from reps_api.content.seed_coding import LONGEST_BUDGET_WINDOW
from reps_api.main import app

TOKEN = "test-internal-token"


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    arena.reset()
    with TestClient(app) as c:
        yield c
    arena.reset()


def test_health_reports_unsandboxed_runner_and_missing_ai_honestly(client):
    body = client.get("/health").json()
    assert body["integrations"]["code_runner"] == "local-subprocess"
    assert body["integrations"]["code_runner_is_sandbox"] is False
    assert body["integrations"]["llm"] is None


def test_internal_routes_need_the_token(client):
    payload = {"spec": {"statement": "s", "task": {"kind": "derivative", "expr": "x^2"}}, "seed": 1}
    assert client.post("/internal/verify/math", json=payload).status_code == 401
    r = client.post("/internal/verify/math", json=payload, headers={"x-internal-token": TOKEN})
    assert r.status_code == 200 and r.json()["status"] == "verified"


def test_exam_flow_over_http(client, store):
    courses = client.get("/api/exam/courses").json()
    assert {c["id"] for c in courses} >= {"calc-1", "phys-kinematics"}
    s = client.post("/api/exam/sessions", json={"course_id": "phys-kinematics"}).json()
    state = client.post(f"/api/exam/sessions/{s['id']}/next").json()
    q = state["current_question"]
    assert q and "answer" not in q and q["verification"]["status"] == "verified"
    key = store.one("select answer from exam_questions where id = ?", (q["id"],))["answer"]
    fb = client.post(f"/api/exam/sessions/{s['id']}/answer", json={"question_id": q["id"], "answer": key}).json()
    assert fb["correct"] and fb["damage"] > 0 and fb["xp"] == 10
    player = client.get("/api/player").json()
    assert player["xp"] == 10 and player["streak"] == 1
    assert client.post("/api/exam/sessions/nope/next").status_code == 404


def test_math_preview(client):
    assert client.post("/api/math/preview", json={"text": "3x^2 + sin(x)"}).json()["latex"] == "3 x^{2} + \\sin{\\left(x \\right)}"
    assert client.post("/api/math/preview", json={"text": "import os"}).json()["error"]


def test_arena_hides_hidden_tests_and_awards_xp_once(client):
    problems = client.get("/api/coding/problems").json()
    assert len(problems) == 6 and problems[0]["difficulty"] == "easy"
    slug = arena.slug(LONGEST_BUDGET_WINDOW.title)
    detail = client.get(f"/api/coding/problems/{slug}").json()
    assert "def solve(minutes, budget):" not in str(detail)
    assert len(detail["examples"]) == len(LONGEST_BUDGET_WINDOW.public_examples)
    first = client.post(f"/api/coding/problems/{slug}/submit", json={"code": LONGEST_BUDGET_WINDOW.reference_solution}).json()
    assert first["verdict"] == "accepted" and first["xp"] == 40
    again = client.post(f"/api/coding/problems/{slug}/submit", json={"code": LONGEST_BUDGET_WINDOW.reference_solution}).json()
    assert again["xp"] == 0
    assert client.get(f"/api/coding/problems/{slug}").json()["status"] == "solved"
    run = client.post(f"/api/coding/problems/{slug}/run", json={"code": "def solve(m, b):\n    return 0"}).json()
    assert run["hidden_total"] == 0
    assert client.post(f"/api/coding/problems/{slug}/run", json={"code": "x", "language": "cpp"}).status_code == 422


def test_upload_without_ai_extracts_and_explains(client):
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), "Limits describe behavior near a point. " * 30, fontsize=10)
    r = client.post("/api/exam/courses/upload", files={"file": ("notes.pdf", doc.tobytes(), "application/pdf")}, data={"name": "My class"})
    body = r.json()
    assert r.status_code == 200 and body["ai_available"] is False and body["preview"]["page_count"] == 1
    bad = client.post("/api/exam/courses/upload", files={"file": ("x.pdf", b"nope", "application/pdf")}, data={"name": "x"})
    assert bad.status_code == 422


def test_interview_over_http(client):
    s = client.post("/api/interview/sessions", json={"role": "quant", "kind": "behavioral", "length": 2}).json()
    q = s["question"]
    out = client.post(
        f"/api/interview/sessions/{s['id']}/answer",
        json={
            "index": q["index"],
            "input_mode": "voice",
            "transcript": "I led it and cut costs by 20 percent, which saved the club money.",
            "audio": {"duration_s": 12, "speaking_s": 9, "pauses_ms": [800]},
        },
    ).json()
    assert out["turn"]["metrics"]["pause_count"] == 1
    rep = client.post(f"/api/interview/sessions/{s['id']}/finish").json()
    assert rep["status"] == "completed" and rep["summary"]["voice_answers"] == 1
