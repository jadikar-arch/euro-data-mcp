"""Summarise a filled-in golden scoresheet per model.

    uv run python eval/golden/score.py eval/golden/scoresheet.csv

Each row is one question for one model; checks are y/n (blank = not graded).
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

CHECKS = ["value_ok", "dataset_ok", "citation_ok", "user_choice_ok", "no_hallucination"]


def main(path: str) -> None:
    per: dict[str, dict[str, list[int]]] = defaultdict(lambda: {c: [0, 0] for c in CHECKS})
    failed: dict[str, list[str]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            model = (row.get("model") or "").strip()
            if not model:
                continue
            for c in CHECKS:
                v = (row.get(c) or "").strip().lower()
                if v in ("y", "n"):
                    per[model][c][1] += 1
                    per[model][c][0] += v == "y"
            if (row.get("value_ok") or "").strip().lower() == "n":
                failed[model].append(row["id"])
    if not per:
        print("No graded rows yet: fill in the model column and y/n checks.")
        return
    print("model|" + "|".join(CHECKS) + "|total")
    for model, s in sorted(per.items()):
        cells = [f"{p}/{n}" if n else "-" for p, n in (s[c] for c in CHECKS)]
        p_all, n_all = sum(s[c][0] for c in CHECKS), sum(s[c][1] for c in CHECKS)
        print(f"{model}|" + "|".join(cells) + f"|{p_all}/{n_all} ({p_all / n_all:.0%})")
    for model, ids in sorted(failed.items()):
        print(f"# {model}: wrong value on {', '.join(ids)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/golden/scoresheet.csv")
