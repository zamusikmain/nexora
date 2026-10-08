"""Save/compare read-only table fingerprints in ignored backups; no data contents are exported."""

import argparse
import re
from pathlib import Path

from verify_role_copy import ROOT, run, source_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save", type=Path)
    group.add_argument("--compare", type=Path)
    args = parser.parse_args()
    path = (args.save or args.compare).resolve()
    if not path.is_relative_to(ROOT / "backups"):
        raise ValueError("State files must remain inside ignored backups")
    container = run(["docker", "compose", "ps", "-q", "db"], capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[a-f0-9]{12,64}", container):
        raise RuntimeError("Working DB is not running")
    current = source_snapshot(container)
    if args.save:
        with path.open("x", encoding="utf-8") as output:
            output.write(current)
        print("Read-only database state saved:", path)
    elif path.read_text(encoding="utf-8") != current:
        raise SystemExit("Table fingerprints differ: do not proceed with cutover")
    else:
        print("All table fingerprints match")


if __name__ == "__main__":
    main()
