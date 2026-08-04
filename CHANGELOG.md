# Changelog

## v0.1.0 - 2026-08-04

First public release. Sanitized from a module that has gated every code review across
a 6-machine agent fleet since 2026-07-21, unchanged since.

- `verdict_contract.py` - `PROMPT_RULE` + strict/weak parser + `exit_code()` gate in
  one file, stdlib only.
- `test_verdict_contract.py` - 42 contract cases plus precedence, fence-desync,
  self-poisoning, loud rendering and exit-code checks. Every case is a counterexample
  produced by a vendor model over seven adversarial review rounds; four of those rounds
  found a real hole in code we already believed was correct.
- `examples/review_gate.py` - wrap any CLI reviewer, verdict reaches the exit status.
- CI on Linux/macOS/Windows x Python 3.9/3.11/3.13, weekly schedule so rot surfaces
  without a push.

Known and deliberate: the weak legacy layer can block but never approve; an APPROVE is
only clean as the single sentinel on the final non-blank line.
