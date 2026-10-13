"""Rules: each one is a function (lines, path) -> iterable[Finding].

Every rule here exists because it broke a real project:

- symlink-copy      : 8 red tests in a bash suite on MSYS (ln -s copies)
- git-posix-path    : 7 red tests + fixture failures: git-for-Windows
                      rejects absolute POSIX temp paths passed as options
- mode-assert       : NTFS cannot store POSIX permission bits (chmod 755
                      reads back as 644), 2 red tests
- tmp-literal       : the POSIX temp directory does not exist outside
                      POSIX-like environments
- tz-path-value     : MSYS path-converts env values containing "/", so
                      TZ=Europe/Paris reached the child process mangled
- long-literal-path : Windows MAX_PATH is 260; a 276-char dependency
                      checkout path failed mid-clone

To add a rule: write a function, register it in RULES, add tests.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, List, Sequence

from .finding import Finding

RuleFn = Callable[[Sequence[str], str], Iterable[Finding]]


def _finding(rule, severity, path, line_no, message, line):
    return Finding(rule, severity, path, line_no, message, line)


# ---------------------------------------------------------------------------
# shell rules
# ---------------------------------------------------------------------------

_SHELL_EXTS = (".sh", ".bash", ".bats", ".zsh")

# ln -s used outside a Windows-symlink gate. The gate is what MSYS shells
# need (MSYS=winsymlinks:nativestrict) or an explicit platform branch.
_LN_S = re.compile(r"(?<![\w-])ln\s+(?:-[a-zA-Z]*[aFf]\s+)*-s\b")
_WINDOWS_GATE = re.compile(r"MINGW|MSYS|CYGWIN|winsymlinks|uname")


def symlink_copy(lines: Sequence[str], path: str):
    """ln -s becomes a plain copy on default MSYS shells; probe or gate it."""
    if not path.endswith(_SHELL_EXTS):
        return
    for i, line in enumerate(lines, 1):
        if not _LN_S.search(line):
            continue
        # A platform gate in the surrounding window (before or after)
        # documents intent: the probe/skip makes this line safe.
        window = lines[max(0, i - 7): i + 4]
        if any(_WINDOWS_GATE.search(w) for w in window):
            continue
        yield _finding(
            "symlink-copy", "warning", path, i,
            "ln -s silently creates a regular file on Windows shells "
            "(MSYS); gate with a platform check or enable "
            "MSYS=winsymlinks:nativestrict after probing it.",
            line,
        )


# git invoked with absolute POSIX paths: git-for-Windows wants C:/... and
# rejects /tmp/... ("fatal: Invalid path") while a `cd` works everywhere.
_GIT_POSIX = re.compile(
    r"""git\s+(?:[\w-]+\s+)*"""
    r"""(?:--work-tree|--git-dir)=(?:"|')?/[a-z]"""
    r"""|\bgit\s+-C\s+(?:"|')?/(?:tmp|var|home|etc|usr|dev)\b"""
)


def git_posix_path(lines: Sequence[str], path: str):
    """Absolute POSIX paths handed to native git break on Windows."""
    if not path.endswith(_SHELL_EXTS):
        return
    for i, line in enumerate(lines, 1):
        if _GIT_POSIX.search(line):
            yield _finding(
                "git-posix-path", "error", path, i,
                "git receives an absolute POSIX path it cannot resolve on "
                "Windows; run it from inside the directory "
                "(`(cd dir && git ...)`) which is portable everywhere.",
                line,
            )


# Permission-bit juggling: NTFS/git-bash cannot represent POSIX modes, so
# chmod-then-assert tests can never pass there.
_CHMOD = re.compile(r"(?<![\w-])chmod\s+(?:-[a-zA-Z]+\s+)*(?:[0-7]{3,4})\b")
_MODE_ASSERT = re.compile(r"assert_(?:file_)?mode|stat\s+-c\s+[\"']%[aA]")


def mode_assert(lines: Sequence[str], path: str):
    """chmod / permission assertions cannot be satisfied on NTFS."""
    if not path.endswith(_SHELL_EXTS):
        return
    for i, line in enumerate(lines, 1):
        if not (_CHMOD.search(line) or _MODE_ASSERT.search(line)):
            continue
        # A platform gate in the surrounding window documents intent: the
        # test skips itself where modes are unrepresentable.
        if any(_WINDOWS_GATE.search(w) for w in lines[max(0, i - 7): i + 4]):
            continue
        yield _finding(
                "mode-assert", "warning", path, i,
                "POSIX permission bits are not representable on NTFS "
                "(chmod 755 reads back as 644); skip such assertions on "
                "MINGW/MSYS/CYGWIN instead of failing.",
                line,
            )


# ---------------------------------------------------------------------------
# file-content rules (any text file we recognize as code/config)
# ---------------------------------------------------------------------------

_TMP_LITERAL = re.compile(r"""(?<![\w/-])/tmp/[A-Za-z0-9._-]""")
_CODE_EXTS = (
    ".sh", ".bash", ".bats", ".zsh", ".py", ".rs", ".go", ".js", ".ts",
    ".yml", ".yaml", ".toml", ".json", ".cfg", ".ini", ".md",
)


def tmp_literal(lines: Sequence[str], path: str):
    """Hardcoded /tmp paths: absent outside POSIX-like environments."""
    if not path.endswith(_CODE_EXTS):
        return
    in_fence = False
    for i, line in enumerate(lines, 1):
        if "mktemp" in line:
            continue
        stripped = line.lstrip()
        if path.endswith(".md"):
            # Prose and tables only describe the problem; code fences show it.
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
        elif stripped.startswith("#"):
            continue
        if _TMP_LITERAL.search(line):
            yield _finding(
                "tmp-literal", "warning", path, i,
                "hard-coded /tmp path is not portable (Windows has no "
                "/tmp); use mktemp or the platform temp directory.",
                line,
            )
            break


# Env assignments whose value looks like a path: MSYS converts env values
# containing "/" before they reach native Windows programs.
_ENV_SLASH = re.compile(
    r"""(?:^|\s)([A-Z][A-Z0-9_]*)=(?:["']?)([A-Za-z][\w-]*/[\w./+-]+)"""
)
_ENV_NAMES = ("TZ", "LANG", "LC_ALL", "LC_TIME", "TZDIR")


def tz_path_value(lines: Sequence[str], path: str):
    """TZ=Europe/Paris-style values get mangled by MSYS env conversion."""
    if not path.endswith(_SHELL_EXTS):
        return
    for i, line in enumerate(lines, 1):
        for m in _ENV_SLASH.finditer(line):
            if m.group(1) not in _ENV_NAMES:
                continue
            yield _finding(
                "tz-path-value", "error", path, i,
                f"{m.group(1)} value containing '/' may be path-converted "
                "by MSYS before reaching native Windows programs; set it "
                "from a .bat/cmd wrapper or strip the value at the boundary.",
                line,
            )
            break


# Long literal paths: Windows MAX_PATH is 260 characters.
def long_literal_path(lines: Sequence[str], path: str):
    """Literal paths longer than Windows' 260-char limit."""
    if not path.endswith(_CODE_EXTS):
        return
    quote_re = re.compile(r"""["']([A-Za-z]:[\\/][^"']{120,}|/[A-Za-z0-9._/-]{120,})["']""")
    for i, line in enumerate(lines, 1):
        for m in quote_re.finditer(line):
            if len(m.group(1)) > 200:
                yield _finding(
                    "long-literal-path", "error", path, i,
                    f"literal path is {len(m.group(1))} characters; Windows "
                    "fails paths beyond 260 (MAX_PATH) unless long-path "
                    "support is enabled everywhere.",
                    line,
                )
                break


RULES: dict = {
    "symlink-copy": (symlink_copy, "warning"),
    "git-posix-path": (git_posix_path, "error"),
    "mode-assert": (mode_assert, "warning"),
    "tmp-literal": (tmp_literal, "warning"),
    "tz-path-value": (tz_path_value, "error"),
    "long-literal-path": (long_literal_path, "error"),
}

RULE_DOCS = {
    "symlink-copy": "ln -s is a copy on default MSYS shells",
    "git-posix-path": "absolute POSIX paths break git-for-Windows",
    "mode-assert": "POSIX permission bits are not representable on NTFS",
    "tmp-literal": "POSIX temp dir does not exist on Windows",
    "tz-path-value": "MSYS path-converts slash-containing env values",
    "long-literal-path": "literal paths beyond Windows MAX_PATH (260)",
}
