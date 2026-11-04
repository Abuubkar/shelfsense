"""Render migration SQL without a database (`alembic upgrade --sql`), for review and for squawk.

    uv run python scripts/render_migrations.py --since origin/main > new.sql   # only what this branch adds
    uv run python scripts/render_migrations.py > all.sql                       # base to head (release artifact)

With --since, revisions whose files exist at that git ref are left out, so squawk lints only new migrations:
applied ones can't change anymore. Prints nothing when there are none.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = "apps/api/migrations/versions"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="a git ref; render only revisions added after it")
    args = parser.parse_args()
    span = "head"
    if args.since:
        existing = set(subprocess.run(["git", "ls-tree", "--name-only", args.since, f"{VERSIONS}/"], cwd=ROOT,
                                      check=True, capture_output=True, text=True).stdout.split())
        script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
        new = [r for r in script.walk_revisions() if f"{VERSIONS}/{Path(r.path).name}" not in existing]
        if not new:
            print(f"no migrations added since {args.since}", file=sys.stderr)
            return
        oldest = new[-1]  # walk_revisions goes from head down
        span = f"{oldest.down_revision}:head" if oldest.down_revision else "head"
    sql = subprocess.run(["alembic", "upgrade", span, "--sql"], cwd=ROOT, check=True, capture_output=True, text=True)
    sys.stdout.write(sql.stdout)


if __name__ == "__main__":
    main()
