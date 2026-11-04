"""Zero-downtime reindex into a new index version (shelfsense_api.reindex, docs/adr/0019).

    uv run python scripts/reindex.py products_v2            # build (resumable), catch up, check; no swap
    uv run python scripts/reindex.py products_v2 --swap     # then: last catch-up, atomic alias move, catch-up
    uv run python scripts/reindex.py products_v2 --rollback # the alias back to the previous version
    uv run python scripts/reindex.py products_v2 --status
    uv run python scripts/reindex.py products_v2 --drop-previous   # only after the 24 h keep

Run `make eval` first: the search eval measures every index version (evals/REPORT.md, "Index versions").
"""

import argparse
import asyncio
import json
import time

from shelfsense_api import reindex
from shelfsense_api.db import SessionLocal
from shelfsense_api.search import TEMPLATES, client


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=sorted(TEMPLATES))
    action = parser.add_mutually_exclusive_group()
    for flag in ("--swap", "--rollback", "--status", "--drop-previous"):
        action.add_argument(flag, action="store_true")
    args = parser.parse_args()
    os = client()
    try:
        async with SessionLocal() as session:
            if args.status:
                print(f"alias serves {await reindex.served_indices(os)}")
                print(json.dumps(await reindex.read_state(os, args.target), indent=2))
                return
            state = await reindex.read_state(os, args.target)
            if args.rollback or args.drop_previous:
                if state is None:
                    raise SystemExit(f"no reindex state on {args.target}")
                if args.rollback:
                    state = await reindex.rollback(os, session, args.target, state)
                    print(f"alias back on {state['previous']}")
                else:
                    print(f"dropped {await reindex.drop_previous(os, session, args.target, state) or 'nothing'}")
                return
            if state is None or state["phase"] in ("building", "built", "checked"):
                started = time.perf_counter()
                state = await reindex.start(os, session, args.target)
                await reindex.build(os, session, args.target, state)
                caught = await reindex.catch_up_target(os, session, args.target, state)
                checks = await reindex.check(os, session, args.target, state)
                print(f"built {state['indexed']} products into {args.target} in {time.perf_counter() - started:.0f}s; "
                      f"catch-up reindexed {caught}")
                print(f"docs: {checks['target_docs']} (Postgres {checks['products']}, {checks['served']} "
                      f"{checks['served_docs']}); parity: {checks['parity_queries'] - len(checks['parity_mismatches'])}"
                      f" of {checks['parity_queries']} queries")
                for m in checks["parity_mismatches"][:10]:
                    print(f"  {m['q']!r}: served {m['served']}, {args.target} {m['target']} (total, found itself)")
                if not checks["passed"]:
                    raise SystemExit("checks failed; the alias was not moved")
            if args.swap:
                state = await reindex.swap(os, session, args.target, state)
                print(f"alias moved {state['previous']} -> {args.target} at {state['swapped_at']}; catch-up before "
                      f"and after: {state['caught_up_around_swap']}; previous kept until {state['keep_until']}")
    finally:
        await os.close()


if __name__ == "__main__":
    asyncio.run(main())
