"""Walk files, apply rules, collect findings."""

from __future__ import annotations

import json
import os
from typing import Iterable, List, Sequence

from .finding import Finding
from .rules import RULES

_SKIP_DIRS = {
    ".git", "node_modules", "target", "dist", "build", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "__pycache__", ".tox", "vendor",
}
_MAX_BYTES = 2_000_000  # skip giant generated files


def load_config(root: str) -> dict:
    """Read .crosslint.json from root if present."""
    path = os.path.join(root, ".crosslint.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def iter_files(paths: Sequence[str]) -> Iterable[str]:
    for raw in paths:
        if os.path.isfile(raw):
            yield raw
            continue
        for dirpath, dirnames, filenames in os.walk(raw):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                yield os.path.join(dirpath, name)


def lint_file(path: str, disabled: Sequence[str] = ()) -> List[Finding]:
    try:
        if os.path.getsize(path) > _MAX_BYTES:
            return []
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    findings: List[Finding] = []
    for rule_id, (fn, default_severity) in RULES.items():
        if rule_id in disabled:
            continue
        for f in fn(lines, path):
            findings.append(
                Finding(f.rule, f.severity or default_severity, f.path,
                        f.line, f.message, f.snippet)
            )
    return findings


def _excluded(path: str, patterns: Sequence[str]) -> bool:
    import fnmatch

    norm = path.replace("\\", "/").removeprefix("./")
    return any(
        fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(os.path.basename(norm), pat)
        for pat in patterns
    )


def lint(paths: Sequence[str], disabled: Sequence[str] = (),
         exclude: Sequence[str] = ()) -> List[Finding]:
    findings: List[Finding] = []
    for path in iter_files(paths):
        if exclude and _excluded(path, exclude):
            continue
        findings.extend(lint_file(path, disabled))
    findings.sort(key=lambda f: (f.path, f.line, f.rule))
    return findings
