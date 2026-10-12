import pymupdf
import pytest
from fastapi.testclient import TestClient

from reps_api.content.seed_coding import LONGEST_BUDGET_WINDOW
from reps_api.main import app

client = TestClient(app)
TOKEN = "test-internal-token"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    monkeypatch.delenv("JUDGE0_URL", raising=False)


def test_health_reports_unsandboxed_runner_honestly():
    body = client.get("/health").json()
    assert body["integrations"]["code_runner"] == "local-subprocess"
    assert body["integrations"]["code_runner_is_sandbox"] is False


def test_internal_routes_need_the_token():
    payload = {"spec": {"statement": "s", "task": {"kind": "derivative", "expr": "x^2"}}, "seed": 1}
    assert client.post("/internal/verify/math", json=payload).status_code == 401
    r = client.post("/internal/verify/math", json=payload, headers={"x-internal-token": TOKEN})
    assert r.status_code == 200 and r.json()["status"] == "verified"


def test_math_grading_endpoint():
    body = {"task": {"kind": "derivative", "expr": "x^3"}, "answer_key": "3*x**2", "student_answer": "3x^2"}
    r = client.post("/internal/grade/math", json=body, headers={"x-internal-token": TOKEN})
    assert r.json()["correct"] is True


def test_problem_detail_hides_hidden_tests_and_solutions():
    problems = client.get("/api/coding/problems").json()
    assert len(problems) == 3
    slug = next(p["slug"] for p in problems if p["title"] == LONGEST_BUDGET_WINDOW.title)
    detail = client.get(f"/api/coding/problems/{slug}").json()
    text = str(detail)
    assert "reference" not in detail and "def solve(minutes, budget):" not in text
    assert len(detail["examples"]) == len(LONGEST_BUDGET_WINDOW.public_examples)
    assert detail["verification"]["cases_run"] >= 300


def test_submit_and_run():
    slug = client.get("/api/coding/problems").json()[0]["slug"]
    good = client.post(f"/api/coding/problems/{slug}/submit", json={"code": LONGEST_BUDGET_WINDOW.reference_solution}).json()
    assert good["verdict"] == "accepted" and good["hidden_total"] > 0
    run = client.post(f"/api/coding/problems/{slug}/run", json={"code": "def solve(m, b):\n    return 0"}).json()
    assert run["hidden_total"] == 0 and run["verdict"] == "wrong_answer"
    assert client.post(f"/api/coding/problems/{slug}/run", json={"code": "x", "language": "cpp"}).status_code == 422
    assert client.post("/api/coding/problems/nope/run", json={"code": "x"}).status_code == 404


def test_pdf_extract_endpoint():
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), "Limits describe behavior near a point. " * 30, fontsize=10)
    r = client.post("/api/documents/extract", files={"file": ("notes.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 200 and r.json()["page_count"] == 1
    bad = client.post("/api/documents/extract", files={"file": ("x.pdf", b"nope", "application/pdf")})
    assert bad.status_code == 422 and "isn't a PDF" in bad.json()["detail"]


def test_boss_next():
    topics = [{"topic_id": "a", "p_known": 0.9, "attempts": 4}, {"topic_id": "b", "p_known": 0.2, "attempts": 4}]
    r = client.post("/api/boss/next", json={"topics": topics, "recent": ["a"]}).json()
    assert r["hp"] == 45
