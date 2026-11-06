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
    assert player["xp"] == 10 + 20 and player["streak"] == 1  # answer + "First blood" badge
    assert [a["key"] for a in player["new_achievements"]] == ["first_hit"]
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
    assert first["verdict"] == "accepted" and first["scale"]["status"] == "fast" and first["xp"] == 40 + 15  # solve + speed bonus
    again = client.post(f"/api/coding/problems/{slug}/submit", json={"code": LONGEST_BUDGET_WINDOW.reference_solution}).json()
    assert again["xp"] == 0
    assert client.get(f"/api/coding/problems/{slug}").json()["status"] == "solved"
    run = client.post(f"/api/coding/problems/{slug}/run", json={"code": "def solve(m, b):\n    return 0"}).json()
    assert run["hidden_total"] == 0
    assert client.post(f"/api/coding/problems/{slug}/run", json={"code": "x", "language": "cpp"}).status_code == 422


def _wait_job(client, job):
    import time

    for _ in range(200):
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.05)
    raise AssertionError("job never finished")


NOTES = """Cell Biology

The cell membrane is a phospholipid bilayer that controls what enters and leaves the cell. Proteins embedded in the membrane act as channels and pumps.

Mitochondria are organelles that produce ATP through cellular respiration. Cellular respiration uses glucose and oxygen and releases carbon dioxide and water.

Osmosis is the diffusion of water across a selectively permeable membrane.
A hypertonic solution has a higher solute concentration than the cell, so water leaves the cell.

Active transport moves molecules against their concentration gradient and requires ATP.
Passive transport does not require ATP because molecules move down their concentration gradient.

Enzymes are proteins that speed up chemical reactions by lowering the activation energy. Each enzyme has an active site that binds a specific substrate.
"""


def test_upload_without_ai_builds_a_boss_from_the_notes(client):
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), "Limits describe behavior near a point. " * 30, fontsize=10)
    r = client.post("/api/exam/courses/upload", files={"files": ("notes.pdf", doc.tobytes(), "application/pdf")}, data={"name": "My class"})
    body = r.json()
    assert r.status_code == 200 and body["ai_available"] is False and body["preview"]["page_count"] == 1
    _wait_job(client, body["job"])
    bad = client.post("/api/exam/courses/upload", files={"files": ("x.pdf", b"nope", "application/pdf")}, data={"name": "x"})
    assert bad.status_code == 422
    assert client.post("/api/exam/courses/upload", data={"name": "x", "text": "too short"}).status_code == 422


def test_pasted_notes_become_a_playable_boss(client, store):
    body = client.post("/api/exam/courses/upload", data={"name": "Bio", "text": NOTES}).json()
    job = _wait_job(client, body["job"])
    assert job["status"] == "succeeded", job
    course_id = job["result"]["course_id"]
    course = next(c for c in client.get("/api/exam/courses").json() if c["id"] == course_id)
    assert course["question_types"] >= 5 and len(course["topics"]) >= 1
    sid = client.post("/api/exam/sessions", json={"course_id": course_id, "length": 5}).json()["id"]
    state = client.post(f"/api/exam/sessions/{sid}/next").json()
    q = state["current_question"]
    assert q["kind"] == "recall" and q["verification"]["checks"][0].startswith("quoted from your notes")
    row = store.one("select answer from exam_questions where id = ?", (q["id"],))
    if q["choices"]:
        assert row["answer"] in q["choices"] and len(q["choices"]) == 4
    r = client.post(f"/api/exam/sessions/{sid}/answer", json={"question_id": q["id"], "answer": row["answer"]}).json()
    assert r["correct"] and r["damage"] > 0 and r["xp"] >= 10 and "From your notes" in r["method"]
    state = client.post(f"/api/exam/sessions/{sid}/next").json()
    q = state["current_question"]
    r = client.post(f"/api/exam/sessions/{sid}/answer", json={"question_id": q["id"], "answer": "definitely not it"}).json()
    assert not r["correct"] and r["hearts_lost"] >= 1


def test_text_files_are_read(client):
    files = [("files", ("week1.txt", NOTES.encode(), "text/plain"))]
    body = client.post("/api/exam/courses/upload", files=files, data={"name": "Bio"}).json()
    assert body["preview"]["files"][0]["name"] == "week1.txt"
    assert _wait_job(client, body["job"])["status"] == "succeeded"


def test_upload_many_pdfs_into_one_course(client):
    def pdf(text, pages):
        doc = pymupdf.open()
        for _ in range(pages):
            doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), text * 30, fontsize=10)
        return doc.tobytes()

    files = [
        ("files", ("week1.pdf", pdf("Limits describe behavior near a point. ", 2), "application/pdf")),
        ("files", ("week2.pdf", pdf("Derivatives measure rates of change. ", 3), "application/pdf")),
    ]
    body = client.post("/api/exam/courses/upload", files=files, data={"name": "Calc"}).json()
    assert body["preview"]["page_count"] == 5 and body["preview"]["filename"] == "2 sources"
    assert [f["name"] for f in body["preview"]["files"]] == ["week1.pdf", "week2.pdf"]
    _wait_job(client, body["job"])


def test_prompt_samples_across_all_material():
    from reps_api.generation import MAX_SOURCE_CHARS, build_prompt
    from reps_api.ingest.pdf import Chunk, Extraction

    chunks = [Chunk(index=i, page_start=i + 1, page_end=i + 1, text=f"[file{i // 50}.pdf] " + "x" * 1000) for i in range(200)]
    prompt = build_prompt("Big", Extraction(pages=[], chunks=chunks, page_count=200, text_pages=200, char_count=200_000))
    assert len(prompt) < MAX_SOURCE_CHARS + 5000
    assert all(f"[file{k}.pdf]" in prompt for k in range(4))  # the last files are represented, not only the first


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
