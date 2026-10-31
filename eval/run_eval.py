"""Score find_data against eval/find_data_cases.json using the live source map.

    uv run python eval/run_eval.py          # build the map if needed, print misses and hit@1/hit@3
    uv run python eval/run_eval.py --fresh  # rebuild the map first

Quote the hit@3 line when you describe search quality, and rerun it after every ranking change.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from europa_mcp import server

CASES = Path(__file__).with_name("find_data_cases.json")


async def main(fresh: bool) -> int:
    smap = server.get_map()
    if fresh:
        await smap.build()
    else:
        await smap.ensure()
    cases = json.loads(CASES.read_text("utf-8"))["cases"]
    hit1 = hit3 = 0
    for c in cases:
        ids = [r["id"] for r in smap.search(c["q"])[:3]]
        ok = {i.lower() for i in c["ok"]}
        rank = next((n for n, i in enumerate(ids, 1) if i.lower() in ok), None)
        hit1 += rank == 1
        hit3 += rank is not None
        if rank is None:
            print(f"MISS  {c['q']!r}: got {ids}, want one of {c['ok']}")
    n = len(cases)
    print(f"\nhit@1 {hit1}/{n} ({hit1 / n:.0%})   hit@3 {hit3}/{n} ({hit3 / n:.0%})")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fresh", action="store_true")
    sys.exit(asyncio.run(main(p.parse_args().fresh)))
