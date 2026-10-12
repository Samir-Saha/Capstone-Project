"""Fit and evaluate BKT on ASSISTments-style data.

Status: pipeline built and tested on synthetic data generated from a known BKT
model. NOT yet run on ASSISTments: the dataset has to be downloaded by hand
(https://sites.google.com/site/assistmentsdata/) because this environment's
network allowlist blocks it.

Input: a CSV with columns user_id, skill_name, correct (0/1), order_id. That's the
layout of the 2009-2010 "skill builder" file; pass --user/--skill/... to remap.

Method
  - Split by student (80/20, seeded), so no student appears in both sets.
    Splitting by row would leak a student's own history into training.
  - Per skill, grid-search (p_init, p_learn, p_slip, p_guess) to maximize
    training log-likelihood. Skills with < 20 training rows use defaults.
  - Predict each test response from that student's earlier responses only,
    then update.
  - Report AUC and RMSE, against a baseline that predicts each skill's
    training-set accuracy.

Usage:
  python eval/assistments_bkt.py data.csv --out eval/results.json
  python eval/assistments_bkt.py --synthetic   # pipeline self-check
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reps_api.tutor.knowledge_tracing import DEFAULT_PARAMS, BKTParams, predict_correct, update

Sequences = dict[str, dict[str, list[int]]]  # skill -> user -> ordered responses

GRID = {
    "p_init": [0.1, 0.3, 0.5, 0.7],
    "p_learn": [0.05, 0.1, 0.2, 0.35],
    "p_slip": [0.05, 0.1, 0.2],
    "p_guess": [0.1, 0.2, 0.3],
}
MIN_ROWS_TO_FIT = 20


def load_csv(path: str, user: str, skill: str, correct: str, order: str) -> list[tuple[str, str, int, float]]:
    rows = []
    with open(path, newline="", encoding="latin-1") as fh:
        for r in csv.DictReader(fh):
            if not r.get(skill) or r.get(correct) not in ("0", "1"):
                continue
            rows.append((r[user], r[skill], int(r[correct]), float(r[order])))
    rows.sort(key=lambda r: r[3])
    return rows


def to_sequences(rows) -> Sequences:
    seqs: Sequences = defaultdict(lambda: defaultdict(list))
    for user, skill, correct, _ in rows:
        seqs[skill][user].append(correct)
    return seqs


def split_users(rows, test_frac: float, seed: int):
    users = sorted({r[0] for r in rows})
    random.Random(seed).shuffle(users)
    cut = int(len(users) * (1 - test_frac))
    train_users = set(users[:cut])
    return [r for r in rows if r[0] in train_users], [r for r in rows if r[0] not in train_users]


def log_likelihood(responses: dict[str, list[int]], params: BKTParams) -> float:
    ll = 0.0
    for seq in responses.values():
        p = params.p_init
        for c in seq:
            pc = min(max(predict_correct(p, params), 1e-6), 1 - 1e-6)
            ll += math.log(pc if c else 1 - pc)
            p = update(p, bool(c), params)
    return ll


def fit_skill(responses: dict[str, list[int]]) -> BKTParams:
    if sum(len(s) for s in responses.values()) < MIN_ROWS_TO_FIT:
        return DEFAULT_PARAMS
    best, best_ll = DEFAULT_PARAMS, -math.inf
    for combo in itertools.product(*GRID.values()):
        kwargs = dict(zip(GRID.keys(), combo))
        if kwargs["p_slip"] + kwargs["p_guess"] >= 1:
            continue
        params = BKTParams(**kwargs)
        ll = log_likelihood(responses, params)
        if ll > best_ll:
            best, best_ll = params, ll
    return best


def auc(labels: list[int], scores: list[float]) -> float:
    """Rank-based AUC (Mann-Whitney U), with tie handling."""
    pairs = sorted(zip(scores, labels))
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    rank_sum = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2  # ranks are 1-based
        rank_sum += avg_rank * sum(lbl for _, lbl in pairs[i:j])
        i = j
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def rmse(labels: list[int], scores: list[float]) -> float:
    return math.sqrt(sum((y - p) ** 2 for y, p in zip(labels, scores)) / len(labels))


def evaluate(rows, test_frac: float = 0.2, seed: int = 7) -> dict:
    train_rows, test_rows = split_users(rows, test_frac, seed)
    train = to_sequences(train_rows)
    test = to_sequences(test_rows)

    fitted = {skill: fit_skill(users) for skill, users in train.items()}
    base_rate = {skill: sum(sum(s) for s in users.values()) / max(1, sum(len(s) for s in users.values())) for skill, users in train.items()}
    overall = sum(r[2] for r in train_rows) / max(1, len(train_rows))

    labels, bkt_scores, base_scores = [], [], []
    for skill, users in test.items():
        params = fitted.get(skill, DEFAULT_PARAMS)
        for seq in users.values():
            p = params.p_init
            for c in seq:
                labels.append(c)
                bkt_scores.append(predict_correct(p, params))
                base_scores.append(base_rate.get(skill, overall))
                p = update(p, bool(c), params)

    return {
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "train_users": len({r[0] for r in train_rows}),
        "test_users": len({r[0] for r in test_rows}),
        "skills": len(train),
        "bkt": {"auc": round(auc(labels, bkt_scores), 4), "rmse": round(rmse(labels, bkt_scores), 4)},
        "baseline_skill_accuracy": {"auc": round(auc(labels, base_scores), 4), "rmse": round(rmse(labels, base_scores), 4)},
        "fitted_params_sample": {k: asdict(v) for k, v in itertools.islice(fitted.items(), 5)},
    }


def synthetic_rows(n_users: int = 300, n_skills: int = 4, length: int = 12, seed: int = 3):
    """Responses simulated from a known BKT model, for checking the pipeline."""
    rng = random.Random(seed)
    truth = {f"skill{k}": BKTParams(p_init=rng.choice([0.1, 0.3]), p_learn=rng.choice([0.1, 0.2]), p_slip=0.1, p_guess=0.2) for k in range(n_skills)}
    rows, order = [], 0
    for u in range(n_users):
        for skill, p in truth.items():
            known = rng.random() < p.p_init
            for _ in range(length):
                correct = (rng.random() > p.p_slip) if known else (rng.random() < p.p_guess)
                rows.append((f"u{u}", skill, int(correct), float(order)))
                order += 1
                if not known and rng.random() < p.p_learn:
                    known = True
    return rows, truth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--user", default="user_id")
    ap.add_argument("--skill", default="skill_name")
    ap.add_argument("--correct", default="correct")
    ap.add_argument("--order", default="order_id")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.synthetic:
        rows, _ = synthetic_rows()
        report = {"dataset": "synthetic (simulated from known BKT parameters)", **evaluate(rows)}
    elif args.csv:
        rows = load_csv(args.csv, args.user, args.skill, args.correct, args.order)
        report = {"dataset": Path(args.csv).name, **evaluate(rows)}
    else:
        ap.error("give a CSV path or --synthetic")

    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
