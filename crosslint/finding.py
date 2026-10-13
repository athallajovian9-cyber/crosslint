"""Findings produced by crosslint rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """One portability hazard at one line of one file."""

    rule: str
    severity: str  # "error" | "warning"
    path: str
    line: int
    message: str
    snippet: str

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "snippet": self.snippet.strip(),
        }

    def as_text(self) -> str:
        return f"{self.path}:{self.line}: {self.severity}: [{self.rule}] {self.message}"
