#!/usr/bin/env node
"use strict";

// npm entry point for crosslint: a thin launcher that runs the bundled
// Python package with any available interpreter. The real implementation
// stays in Python (one codebase, one source of truth); this shim only
// makes `npx crosslint` work for people who live in npm.

const { spawnSync } = require("child_process");
const path = require("path");

const lib = path.join(__dirname, "..", "lib");

function findPython() {
  const candidates = process.platform === "win32"
    ? ["python", "python3", "py"]
    : ["python3", "python"];
  for (const cand of candidates) {
    const probe = spawnSync(cand, ["-c", "import sys"], { stdio: "ignore" });
    if (probe.status === 0) return cand;
  }
  console.error(
    "crosslint: no usable Python interpreter found (tried " +
      candidates.join(", ") +
      ").\nInstall Python 3.9+ or use the pip package instead."
  );
  process.exit(1);
}

const env = Object.assign({}, process.env, {
  PYTHONPATH: lib + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
});

const res = spawnSync(findPython(), ["-m", "crosslint", ...process.argv.slice(2)], {
  stdio: "inherit",
  env,
});

if (res.error) {
  console.error("crosslint: " + res.error.message);
  process.exit(1);
}
process.exit(res.status === null ? 1 : res.status);
