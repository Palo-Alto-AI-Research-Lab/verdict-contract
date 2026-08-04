# AGENTS.md - how to change this repo (human or agent)

Short on purpose. The repo is one module, one test, one example.

## What this repo is

A **contract**, not a library: the instruction a reviewer model receives and the parser
that reads its reply, in one file, so they cannot drift apart. People copy
`verdict_contract.py` into their own tooling and edit it. Clarity and honest failure
modes are worth more here than features.

## Non-negotiables

1. **Stdlib only, Python 3.8+.** This file gets vendored into other people's CI. A
   dependency would have to be installed everywhere a review runs.
2. **One file holds both sides.** If you add a prompt rule, it goes in `PROMPT_RULE`
   next to the parser that enforces it. Never retype the rule into a caller - import it.
   Callers that retype it are how the contract fails silently.
3. **The asymmetry is not a bug.** Blocking wins from anywhere; approving requires the
   exact shape. A false block costs a re-read, a false approve ships a bug. Any change
   that makes APPROVE easier to reach needs to argue against that sentence.
4. **The strict layer never depends on fence detection.** It is undecidable on
   nested/unbalanced fences and it flipped a real block into an approve in production.
   Best-effort fence stripping feeds only the weak layer, which cannot approve.
5. **The exit-code contract is fixed**: `0` approve, `3` request-changes, `4` ambiguous
   or not stated. `1`/`2` stay free for script and usage errors.
6. **Every change adds a counterexample.** New behaviour means a new case in
   `test_verdict_contract.py` that plants the exact reply text it exists to catch. A
   test that only covers the happy path measures nothing.

## The most useful contribution

A reply string that this parser reads wrong. Open an issue with the **verbatim model
output** and what you expected. Every case in the test file arrived that way.
