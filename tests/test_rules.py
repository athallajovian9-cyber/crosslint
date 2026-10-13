"""Every rule is tested with a triggering sample and a clean sample.

Each triggering case is taken from a real failure: the bash-suite port to
Windows (36 red tests in four clusters), a TZ env probe that lied for an
hour under MSYS, and a 276-char dependency checkout that died at MAX_PATH.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from crosslint.engine import lint, lint_file
from crosslint.rules import RULES
from crosslint import Finding


def findings_for(rule, source, name="sample.sh"):
    path = os.path.join(str(pytest.importorskip("tempfile").gettempdir()), name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(source)
    return [f for f in lint_file(path) if f.rule == rule]


class TestSymlinkCopy:
    TRIGGER = "# setup\nprepare() {\n  ln -s \"$fixture/a\" \"$dir/a\"\n}\n"
    CLEAN = (
        "case \"$(uname)\" in\n  MINGW*|MSYS*)\n    MSYS=winsymlinks:nativestrict ln -s a b\n  ;;\nesac\n"
    )

    def test_flags_plain_symlink(self):
        fs = findings_for("symlink-copy", self.TRIGGER)
        assert len(fs) == 1
        assert fs[0].line == 3
        assert fs[0].severity == "warning"

    def test_accepts_gated_symlink(self):
        assert findings_for("symlink-copy", self.CLEAN) == []

    def test_ignores_non_shell_files(self):
        assert findings_for("symlink-copy", self.TRIGGER, "x.py") == []


class TestGitPosixPath:
    TRIGGER = 'git --work-tree="/tmp/wt" --git-dir="/tmp/wt/.git" init\n'
    TRIGGER_C = 'git -C /tmp/repo status\n'
    CLEAN = '(cd "${dir}" && git init)\n(cd /tmp/x && git status)\n'

    def test_flags_work_tree(self):
        fs = findings_for("git-posix-path", self.TRIGGER)
        assert len(fs) == 1
        assert fs[0].severity == "error"

    def test_flags_dash_c(self):
        assert findings_for("git-posix-path", self.TRIGGER_C)

    def test_accepts_cd_form(self):
        assert findings_for("git-posix-path", self.CLEAN) == []


class TestModeAssert:
    TRIGGER = "chmod 755 \"$bin/tool\"\nstat -c '%a' \"$f\" > out\n"
    CLEAN = (
        'case "$(uname)" in\n  MINGW*|MSYS*) skip "no modes on NTFS" ;;\nesac\nchmod 755 f\n'
    )

    def test_flags_chmod(self):
        fs = findings_for("mode-assert", self.TRIGGER)
        assert len(fs) == 2

    def test_accepts_gated(self):
        # the gate window covers the chmod on the last line
        assert findings_for("mode-assert", self.CLEAN) == []


class TestTmpLiteral:
    TRIGGER = 'cfg="/tmp/app/config.toml"\n'
    CLEAN = 'cfg="$(mktemp -d)"/config.toml\n'

    def test_flags_tmp(self):
        fs = findings_for("tmp-literal", self.TRIGGER, "app.py")
        assert len(fs) == 1

    def test_accepts_mktemp(self):
        assert findings_for("tmp-literal", self.CLEAN, "app.py") == []


class TestTzPathValue:
    TRIGGER = 'TZ=Europe/Paris ./run-tests\n'
    CLEAN = 'TZ=UTC0 ./run-tests\nTZ=UTC ./run-tests\n'

    def test_flags_slash_value(self):
        fs = findings_for("tz-path-value", self.TRIGGER)
        assert len(fs) == 1
        assert "TZ" in fs[0].message

    def test_accepts_posix_tz(self):
        assert findings_for("tz-path-value", self.CLEAN) == []


class TestLongLiteralPath:
    TRIGGER = 'url = "' + "C:/cache/checkouts/very-long-directory-name/" + ("segment/" * 30) + 'file.snap"\n'
    CLEAN = 'path = "C:/cache/dir/file.txt"\n'

    def test_flags_long_path(self):
        fs = findings_for("long-literal-path", self.TRIGGER, "Cargo.toml")
        assert len(fs) == 1
        assert fs[0].severity == "error"

    def test_accepts_short_path(self):
        assert findings_for("long-literal-path", self.CLEAN, "Cargo.toml") == []


class TestEngineAndCli:
    def test_all_rules_registered(self):
        assert set(RULES) == {
            "symlink-copy", "git-posix-path", "mode-assert",
            "tmp-literal", "tz-path-value", "long-literal-path",
        }

    def test_lint_directory_skips_vendored(self, tmp_path):
        (tmp_path / "keep.sh").write_text('cfg="/tmp/x/y"\n', encoding="utf-8")
        vendored = tmp_path / "node_modules"
        vendored.mkdir()
        (vendored / "bad.sh").write_text('cfg="/tmp/x/y"\n', encoding="utf-8")
        fs = lint([str(tmp_path)])
        assert len(fs) == 1
        assert fs[0].path.endswith("keep.sh")

    def test_exclude_patterns(self, tmp_path):
        bad = tmp_path / "fixtures"
        bad.mkdir()
        (bad / "bad.sh").write_text('cfg="/tmp/x/y"\n', encoding="utf-8")
        (tmp_path / "ok.sh").write_text('cfg="/tmp/x/y"\n', encoding="utf-8")
        fs = lint([str(tmp_path)], exclude=["*/fixtures/*"])
        assert len(fs) == 1
        assert fs[0].path.endswith("ok.sh")

    def test_disable_rule(self, tmp_path):
        p = tmp_path / "a.sh"
        p.write_text('cfg="/tmp/x/y"\n', encoding="utf-8")
        assert lint([str(tmp_path)], disabled=["tmp-literal"]) == []

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "crosslint", *args],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )

    def test_cli_error_fails(self, tmp_path):
        p = tmp_path / "bad.sh"
        p.write_text('git -C /tmp/repo status\n', encoding="utf-8")
        r = self.run_cli(str(p))
        assert r.returncode == 1
        assert "git-posix-path" in r.stdout

    def test_cli_warning_passes_by_default(self, tmp_path):
        p = tmp_path / "warn.sh"
        p.write_text('cfg="/tmp/x/y"\n', encoding="utf-8")
        r = self.run_cli(str(p))
        assert r.returncode == 0
        assert "tmp-literal" in r.stdout

    def test_cli_json(self, tmp_path):
        import json

        p = tmp_path / "bad.sh"
        p.write_text('git -C /tmp/repo status\n', encoding="utf-8")
        r = self.run_cli(str(p), "--format", "json")
        data = json.loads(r.stdout)
        assert data[0]["rule"] == "git-posix-path"

    def test_cli_list_rules(self):
        r = self.run_cli("--list-rules")
        assert r.returncode == 0
        assert "symlink-copy" in r.stdout
