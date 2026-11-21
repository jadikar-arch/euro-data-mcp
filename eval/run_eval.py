"""Score find_data against eval/find_data_cases.json using the live source map.

    uv run python eval/run_eval.py          # build the map if needed, print misses and hit@1/hit@3
    uv run python eval/run_eval.py --fresh  # rebuild the map first
    uv run python eval/run_eval.py --set holdout  # questions never used for tuning (the honest score)

Quote the hit@3 line when you describe search quality, and rerun it after every ranking change.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from europa_mcp import server

SETS = {"dev": "find_data_cases.json", "holdout": "find_data_holdout.json"}


async def main(fresh: bool, min_hit3: float, which: str) -> int:
    smap = server.get_map()
    if fresh:
        await smap.build()
    else:
        await smap.ensure()
    cases = json.loads(Path(__file__).with_name(SETS[which]).read_text("utf-8"))["cases"]
    hit1 = hit3 = 0
    for c in cases:
        ids = [r["id"] for r in server.ranked_matches(c["q"], None, 4, 10)[:3]]  # what find_data shows first
        ok = {i.lower() for i in c["ok"]}
        rank = next((n for n, i in enumerate(ids, 1) if i.lower() in ok), None)
        hit1 += rank == 1
        hit3 += rank is not None
        if rank is None:
            print(f"MISS  {c['q']!r}: got {ids}, want one of {c['ok']}")
    n = len(cases)
    print(f"\nhit@1 {hit1}/{n} ({hit1 / n:.0%})   hit@3 {hit3}/{n} ({hit3 / n:.0%})")
    if hit3 / n < min_hit3:
        print(f"FAIL: hit@3 below the required {min_hit3:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--set", choices=SETS, default="dev", help="dev: tuned on; holdout: never tuned on")
    p.add_argument("--min-hit3", type=float, default=0.0, help="exit 1 if hit@3 is below this share (0-1)")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.fresh, a.min_hit3, a.set)))
