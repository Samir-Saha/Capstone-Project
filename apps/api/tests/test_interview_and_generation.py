import json
import random

import pymupdf
import pytest

from reps_api import generation, interview
from reps_api.ingest.pdf import extract_pdf
from reps_api.interview import AnswerIn, AudioMetrics, StartInterview
from reps_api.llm import LLMError, ScriptedProvider, generate_structured

RESUME = """Samir Example
Experience
AI Developer Intern, Example Startup
• Built a retrieval pipeline in Python and FastAPI that cut average answer latency by 40%
  for 10,000+ users
• Led a team of 3 to ship a React dashboard
Projects
• Developed a World Cup match predictor with scikit-learn and pandas
• Organized weekly volunteer events across five states
"""


def test_claims_join_wrapped_lines_and_find_metrics():
    claims = interview.extract_claims(RESUME)
    texts = [c.text for c in claims]
    assert any("40%" in t and "10,000+ users" in t for t in texts)
    latency = next(c for c in claims if "40%" in c.text)
    assert latency.measurable and {"python", "fastapi"} <= set(latency.technologies)
    predictor = next(c for c in claims if "predictor" in c.text)
    assert not predictor.measurable


def test_fillers_and_measured_delivery():
    a = AnswerIn(
        index=0,
        input_mode="voice",
        transcript="Um so I basically built it, you know, and uh it cut latency by 40 percent.",
        audio=AudioMetrics(duration_s=30, speaking_s=20, pauses_ms=[300, 700, 2500]),
    )
    m = interview.measure(a)
    assert m["fillers"] == {"um": 1, "uh": 1, "you know": 1, "basically": 1}
    assert m["pause_count"] == 2 and m["long_pauses"] == 1
    assert m["wpm"] == round(m["words"] / (20 / 60))
    typed = interview.measure(AnswerIn(index=0, input_mode="text", transcript="I did it."))
    assert "wpm" not in typed and "not measured" in typed["source"]


def test_rule_based_follow_ups():
    vague = AnswerIn(index=0, input_mode="text", transcript="We built it and we shipped it and our team was happy with it.")
    chk = interview.checks(vague, "resume")
    assert interview.follow_up({"kind": "resume"}, chk).startswith("How did you measure")
    chk = interview.checks(vague, "behavioral")
    assert "we" in interview.follow_up({"kind": "behavioral"}, chk)


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 570, 800), text, fontsize=10)
    return doc.tobytes()


def test_full_interview_without_ai(store):
    resume = interview.upload_resume(store, "resume.pdf", _pdf(RESUME))
    assert resume["claims"]
    s = interview.start(store, StartInterview(role="software", kind="behavioral", length=3, resume_id=resume["id"]), rng=random.Random(1))
    assert s["question"]["kind"] in ("resume", "behavioral")
    total = s["total"]
    answered = 0
    while s["question"]:
        out = interview.submit(
            store,
            s["id"],
            AnswerIn(index=s["question"]["index"], input_mode="text", transcript="We worked on it together and it went fine overall."),
        )
        answered += 1
        s = out["session"]
    assert answered > total  # vague answers triggered follow-ups
    report = interview.finish(store, s["id"])
    assert report["status"] == "completed" and not report["ai_scored"]
    assert report["xp"] == 30
    assert any("number" in f for f in report["focus"])


def test_technical_question_runs_code(store):
    s = interview.start(store, StartInterview(role="software", kind="technical", length=2), rng=random.Random(2))
    q = s["question"]
    assert q["kind"] == "technical" and q["problem"]["starter_code"]
    out = interview.submit(store, s["id"], AnswerIn(index=0, input_mode="text", transcript="I'd scan once with a stack. " * 6, code=q["problem"]["starter_code"]))
    assert out["turn"]["checks"]["code"]["verdict"] == "wrong_answer"


def test_ai_star_scoring_drops_invented_quotes(store):
    s = interview.start(store, StartInterview(role="software", kind="behavioral", length=2), rng=random.Random(3))
    for i in range(2):
        txt = "I led the migration, I measured p95 latency before and after, and it dropped from 900 ms to 300 ms."
        s = interview.submit(store, s["id"], AnswerIn(index=i, input_mode="text", transcript=txt))["session"]
    reply = {
        "answers": [
            {
                "index": 0,
                "situation": 2,
                "task": 3,
                "action": 4,
                "result": 4,
                "specificity": 4,
                "strengths": ["numbers"],
                "missing": [],
                "improvement": "Set the scene first.",
                "quote": "it dropped from 900 ms to 300 ms",
            },
            {
                "index": 1,
                "situation": 2,
                "task": 3,
                "action": 4,
                "result": 4,
                "specificity": 4,
                "strengths": [],
                "missing": [],
                "improvement": "x",
                "quote": "a sentence the candidate never said",
            },
        ]
    }
    provider = ScriptedProvider([json.dumps(reply)])
    report = interview.finish(store, s["id"], provider=provider)
    assert report["ai_scored"]
    fb = {t["index"]: t["ai_feedback"] for t in report["turns"]}
    assert fb[0]["quote"] == "it dropped from 900 ms to 300 ms"
    assert fb[1]["quote"] is None
    assert "<untrusted>" in provider.calls[0]["messages"][0]["content"]


# ------------------------------------------------------------------ structured output


def test_structured_output_repairs_once_then_fails():
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    ok = ScriptedProvider(["not json", '```json\n{"n": 3}\n```'])
    assert generate_structured(ok, "s", "u", Out, "t").n == 3
    bad = ScriptedProvider(["nope", '{"n": "three"}'])
    with pytest.raises(LLMError):
        generate_structured(bad, "s", "u", Out, "t")


# ------------------------------------------------------------------ course generation


NOTES = (
    "Lecture 4: The power rule. For any integer n, the derivative of x^n is n x^(n-1). "
    "Example: the derivative of 5x^3 is 15x^2. " * 3 + "Lecture 5: Definite integrals. The integral of x^2 from 0 to b equals b^3/3. " * 3
)


def test_generation_keeps_only_grounded_verified_templates(store):
    extraction = extract_pdf(_pdf(NOTES))
    plan = {
        "boss_name": "The Power Warden",
        "topics": [
            {
                "name": "Power rule",
                "description": "Derivatives of powers",
                "templates": [
                    {
                        "prompt": "Find the derivative.",
                        "kind": "derivative",
                        "expr": "{a}*x^{n}",
                        "params": {"a": {"min": 2, "max": 9}, "n": {"min": 2, "max": 5}},
                        "claimed_answer": "{a}*{n}*x^({n}-1)",
                        "difficulty": 1,
                        "hint": "power rule",
                        "method": "n x^(n-1)",
                        "numeric_answer": False,
                        "source_chunk": 0,
                        "source_quote": "the derivative of x^n is n x^(n-1)",
                    },
                    {
                        "prompt": "Find the derivative.",
                        "kind": "derivative",
                        "expr": "{a}*x^3",
                        "params": {"a": {"min": 2, "max": 9}},
                        "claimed_answer": "{a}*x^2",
                        "difficulty": 1,
                        "hint": "h",
                        "method": "m",
                        "numeric_answer": False,
                        "source_chunk": 0,
                        "source_quote": "the derivative of x^n is n x^(n-1)",
                    },
                    {
                        "prompt": "Find the derivative.",
                        "kind": "derivative",
                        "expr": "x^2",
                        "claimed_answer": "2*x",
                        "difficulty": 1,
                        "hint": "h",
                        "method": "m",
                        "numeric_answer": False,
                        "source_chunk": 0,
                        "source_quote": "a quote that is not in the notes",
                    },
                ],
            }
        ],
    }
    provider = ScriptedProvider([json.dumps(plan)])
    store.run("insert into jobs (id, kind, status, progress, created_at) values ('j', 'generate_course', 'running', '{}', 'now')")
    store.run("insert into documents (id, filename, status, created_at) values ('d', 'notes.pdf', 'processing', 'now')")
    result = generation.generate_course(store, provider, "Calc notes", extraction, "j", "d")
    assert result["ai_kept"] == 1 and result["ai_rejected"] == 2
    course = store.one("select * from courses where id = ?", (result["course_id"],))
    assert course["boss_name"] == "The Power Warden"
    reasons = {r["reason"] for r in store.all("select reason from verification_log where subject = 'generated_template' and status = 'rejected'")}
    assert "source quote not found in the material" in reasons
    assert "generator's claimed answer is wrong" in reasons
