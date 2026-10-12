import random
import sys
from pathlib import Path

import pymupdf
import pytest

from reps_api.ingest.pdf import ExtractionError, Page, chunk_pages, extract_pdf
from reps_api.tutor.knowledge_tracing import (
    BKTParams,
    BossPolicy,
    TopicMastery,
    boss_hp,
    fresh,
    update,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import assistments_bkt

# ------------------------------------------------------------------ BKT


def test_update_direction_and_bounds():
    p = 0.3
    assert update(p, True) > p
    assert update(p, False) < update(p, True)
    for _ in range(200):
        p = update(p, random.random() < 0.5)
        assert 0 <= p <= 1


def test_hand_computed_update():
    params = BKTParams(p_init=0.3, p_learn=0.1, p_slip=0.1, p_guess=0.2)
    # posterior = .3*.9 / (.3*.9 + .7*.2) = .27/.41
    post = 0.27 / 0.41
    assert update(0.3, True, params) == pytest.approx(post + (1 - post) * 0.1)


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        BKTParams(p_slip=0.6, p_guess=0.5)
    with pytest.raises(ValueError):
        BKTParams(p_init=0.0)


def test_provisional_until_enough_evidence():
    t = fresh("t")
    assert t.provisional
    for _ in range(3):
        t = t.record(True)
    assert not t.provisional and t.attempts == 3 and t.correct == 3


def test_boss_hp_tracks_mastery():
    weak = [TopicMastery("a", 0.1), TopicMastery("b", 0.2)]
    strong = [TopicMastery("a", 0.9), TopicMastery("b", 0.95)]
    assert boss_hp(weak) == 85 and boss_hp(strong) == 7
    assert boss_hp([]) == 100


def test_boss_covers_every_topic_before_repeating():
    policy = BossPolicy(rng=random.Random(0))
    topics = [fresh(t) for t in "abcd"]
    asked = []
    for _ in range(4):
        nxt = policy.next_topic(topics, asked)
        asked.append(nxt)
        topics = [t.record(False) if t.topic_id == nxt else t for t in topics]
    assert sorted(asked) == list("abcd")


def test_boss_targets_weakness_without_letting_it_dominate():
    policy = BossPolicy(explore=0.0, rng=random.Random(0))
    topics = [TopicMastery("weak", 0.05, attempts=5), TopicMastery("ok", 0.6, attempts=5), TopicMastery("good", 0.9, attempts=5)]
    assert policy.next_topic(topics, ["ok"]) == "weak"
    assert policy.next_topic(topics, ["weak", "weak"]) != "weak"
    seq = []
    for _ in range(30):
        seq.append(policy.next_topic(topics, seq))
    assert seq.count("weak") < 30 and seq.count("weak") > seq.count("good")


# ------------------------------------------------------------------ evaluation pipeline


def test_auc_matches_known_values():
    assert assistments_bkt.auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert assistments_bkt.auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5
    assert assistments_bkt.auc([1, 0], [0.1, 0.9]) == 0.0


def test_pipeline_beats_baseline_on_bkt_generated_data():
    rows, _ = assistments_bkt.synthetic_rows(n_users=150, n_skills=2)
    report = assistments_bkt.evaluate(rows)
    assert report["bkt"]["auc"] > report["baseline_skill_accuracy"]["auc"] + 0.1
    assert report["train_users"] + report["test_users"] == 150


def test_split_is_by_student():
    rows, _ = assistments_bkt.synthetic_rows(n_users=50, n_skills=1, length=3)
    train, test = assistments_bkt.split_users(rows, 0.2, seed=1)
    assert not ({r[0] for r in train} & {r[0] for r in test})


# ------------------------------------------------------------------ PDF ingest


def _pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_extracts_text_with_page_numbers():
    body = "Integration by parts: the integral of u dv equals uv minus the integral of v du. " * 8
    result = extract_pdf(_pdf([body, "Taylor series approximate smooth functions with polynomials. " * 8]))
    assert result.page_count == 2 and result.text_pages == 2
    assert result.chunks and result.chunks[0].page_start == 1
    assert any(c.page_end == 2 for c in result.chunks)


def test_scanned_pdf_is_refused():
    with pytest.raises(ExtractionError, match="scanned"):
        extract_pdf(_pdf(["", "", ""]))


@pytest.mark.parametrize("data", [b"hello", b"%PDF-1.7 garbage"])
def test_bad_files_are_refused(data):
    with pytest.raises(ExtractionError):
        extract_pdf(data)


def test_chunks_respect_target_and_keep_everything():
    pages = [Page(1, "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(20)))]
    chunks = chunk_pages(pages, target=600, overlap=100)
    assert len(chunks) > 3
    assert all(len(c.text) <= 600 + 100 + 250 for c in chunks)
    joined = " ".join(c.text for c in chunks)
    assert all(f"Paragraph {i} " in joined for i in range(20))
