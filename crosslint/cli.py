"""crosslint command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence

from .engine import lint, load_config
from .rules import RULE_DOCS, RULES

__version__ = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crosslint",
        description="Find portability hazards (Windows/macOS/Linux) before "
        "CI does.",
    )
    p.add_argument("paths", nargs="*", default=["."],
                   help="files or directories to lint (default: .)")
    p.add_argument("--format", choices=("text", "json"), default="text")
    p.add_argument("--disable", default="",
                   help="comma-separated rule ids to disable")
    p.add_argument("--fail-on", choices=("error", "warning", "never"),
                   default="error",
                   help="minimum severity that makes the exit code 1 "
                        "(default: error)")
    p.add_argument("--list-rules", action="store_true",
                   help="print all rules and exit")
    p.add_argument("--version", action="version",
                   version=f"crosslint {__version__}")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_rules:
        for rule_id, doc in RULE_DOCS.items():
            severity = RULES[rule_id][1]
            print(f"{rule_id:18} [{severity:7}] {doc}")
        return 0

    config = load_config(".")
    disabled = set(config.get("disable", []))
    disabled.update(r for r in args.disable.split(",") if r)
    exclude = config.get("exclude", [])

    findings = lint(args.paths, sorted(disabled), exclude)

    if args.format == "json":
        print(json.dumps([f.as_dict() for f in findings], indent=2))
    else:
        for f in findings:
            print(f.as_text())
        if findings:
            errors = sum(1 for f in findings if f.severity == "error")
            warnings = len(findings) - errors
            print(f"crosslint: {errors} error(s), {warnings} warning(s)",
                  file=sys.stderr)

    if args.fail_on == "never" or not findings:
        return 0
    if args.fail_on == "warning":
        return 1
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
