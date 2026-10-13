# crosslint

**Find portability hazards (Windows / macOS / Linux) in test suites and
scripts — before your CI does.**

`ln -s` is a copy on Windows shells. `git --work-tree="/tmp/..."` is an
invalid path to git-for-Windows. `chmod 755` reads back as `644` on NTFS.
MSYS quietly rewrites `TZ=Europe/Paris` before it reaches the child
process. None of these fail on Linux — so they fail *for your users and
your Windows contributors*, usually as a wall of red tests nobody can
explain.

crosslint is a tiny zero-dependency linter that spots exactly this class
of bug from the command line:

```console
$ crosslint tests/
tests/assert.file.bats:83: warning: [symlink-copy] ln -s silently creates a regular file on Windows shells ...
tests/git_helpers.sh:12: error: [git-posix-path] git receives an absolute POSIX path it cannot resolve on Windows ...
crosslint: 1 error(s), 1 warning(s)
```

## Why

Every rule in crosslint exists because it broke a real project first:

| rule | real incident |
|---|---|
| `symlink-copy` | 8 red tests in a bash suite: `ln -s` copies on MSYS |
| `git-posix-path` | 7 red tests + broken fixtures: git-for-Windows rejects `/tmp/...` |
| `mode-assert` | `chmod 755` cannot be represented on NTFS — tests that can *never* pass |
| `tmp-literal` | the POSIX temp dir does not exist outside POSIX-like environments |
| `tz-path-value` | MSYS path-converts env values containing `/`; a probe can lie to you for an hour |
| `long-literal-path` | a 276-character dependency checkout path died at Windows' 260-char `MAX_PATH` |

## Install

```console
$ pip install crosslint        # PyPI
$ npm install -g crosslint     # npm (same Python core via a Node launcher)
```

Or from source — no dependencies, Python 3.9+:

```console
$ pip install git+https://github.com/athallajovian9-cyber/crosslint
$ python -m crosslint tests/ scripts/
```

Both registry packages ship the identical Python implementation: the npm
package only adds a launcher, so there is exactly one linter to keep correct.

## Usage

```console
$ crosslint --list-rules
symlink-copy        [warning] ln -s is a copy on default MSYS shells
git-posix-path      [error  ] absolute POSIX paths break git-for-Windows
mode-assert         [warning] POSIX permission bits are not representable on NTFS
tmp-literal         [warning] /tmp does not exist on Windows
tz-path-value       [error  ] MSYS path-converts slash-containing env values
long-literal-path   [error  ] literal paths beyond Windows MAX_PATH (260)

$ crosslint --format json tests/     # machine-readable
$ crosslint --disable tmp-literal .  # per-run opt-out
$ crosslint --fail-on warning .      # CI-strict mode (exit 1 on warnings too)
```

Exit codes: `0` = nothing at or above `--fail-on` (default: `error`),
`1` = findings. Drop a `.crosslint.json` at the repo root for sticky
config:

```json
{ "disable": ["tmp-literal"] }
```

## Contributing

Issues and pull requests are open. The full credit policy (your PR keeps
your authorship, no CLA) lives in
[CONTRIBUTORS.md](https://github.com/athallajovian9-cyber/crosslint/blob/main/CONTRIBUTORS.md).
Short version: open an issue describing the incident first, then send one
function + one test.

## Adding a rule

One function + one test = a complete contribution. Rules live in
`crosslint/rules.py`, are registered in the `RULES` dict, and get a one-line
description in `RULE_DOCS`. Document the *real incident* that proves the
rule — that's the bar.

```python
def my_rule(lines, path):
    for i, line in enumerate(lines, 1):
        if bad(line):
            yield Finding("my-rule", "warning", path, i, "what breaks and where", line)
```

Open an issue first for rules that fire outside shell/build files —
false positives are worse than missed detections.

## Scope

crosslint reads files as text and pattern-matches. It does not execute
anything, needs no network, and has no dependencies. It complements
platform CI: CI proves what happens, crosslint predicts it.

## License

MIT
