# verdict-contract

**Your LLM reviewer said APPROVE. Did it?**

If you pipe a diff to a model and grep its reply for `VERDICT: APPROVE`, you do not have a
gate — you have a coin flip that fails in the dangerous direction, and `test_verdict_contract.py`
shows five ways it does.

This repo is the stdlib-only module that replaced ours — 197 lines in `verdict_contract.py` —
plus the 42 counterexamples that forced every line of it, all of them runnable as
`test_verdict_contract.py`.

MIT. No dependencies. Python 3.8+. Copy one file and go.

---

## The failure it fixes

We ran a real two-vendor review gate over our own diffs, then asked the two vendors to
review the gate itself; both independently answered `ROOT-FIXED: NO`.
Every counterexample below is reproduced live by `test_verdict_contract.py`, and the
afternoon they came from is written up in
[devlog/2026-08-04-seven-rounds-to-a-verdict.md](devlog/2026-08-04-seven-rounds-to-a-verdict.md):

| what the model wrote | what the old parser read | why it matters |
|---|---|---|
| `I refuse to give a VERDICT`<br>`APPROVE would be wrong` | APPROVE | `\s` in the gap class quietly includes `\n` |
| `Example output: VERDICT: APPROVE` | APPROVE | a quoted example shipped as a real pass |
| the prompt text itself, echoed back | APPROVE | the instruction contained both literals: prompt self-poisoning |
| `## VERDICT: REQUEST_CHANGES` | *(nothing)* | a silent miss: review happened, no verdict recorded, nobody shouting |
| a blocking review, printed then exit 0 | "the review passed" | the verdict never reached the exit code |

The last one is the whole category: a gate whose verdict lives only in stdout is not a
gate, it is a log line. The exit-code half of the fix lives in `verdict_contract.py`.

And one that only shows up in production: a reviewer quoted a bare ` ``` ` **inside** a
` ```text ` block, our fence tracker desynced, a quoted APPROVE became "visible", and the
gate approved a diff the reviewer had just rejected. Fence detection is undecidable on
nested or unbalanced fences, so the strict layer does not use it at all — the case is
pinned as `fence-desync` in `test_verdict_contract.py`.

## The fix, in four parts

All four are implemented in `verdict_contract.py` and each has its own cases in `test_verdict_contract.py`:

1. **Structured marker** (`_SENTINEL_MARK` in `verdict_contract.py`). The model must emit
   `===VERDICT=== <value>` alone on its final line; the parser matches whole lines only,
   so prose can never glue into a verdict and a newline gap is impossible by construction.
2. **Closed enum, explicit AMBIGUOUS, position enforced** (`find_verdict` in `verdict_contract.py`).
   `APPROVE` or `REQUEST_CHANGES`, nothing else — a junk value, contradicting markers, a
   repeated marker, or an APPROVE that is not the final non-blank line all return `AMBIGUOUS`
   loudly. Never a guess, never a silent fail-safe.
3. **The weak layer can block but never approve** (`_WEAK` in `verdict_contract.py`).
   Old-style prose verdicts still block (safe direction); a prose approve degrades to
   `AMBIGUOUS`. **The asymmetry is the design**: a false block costs a re-read, a false
   approve ships a bug.
4. **Exit-code gate** (`exit_code` in `verdict_contract.py`). `0` approve, `3` request-changes,
   `4` ambiguous or missing — automation can no longer read "it printed something" as "it passed".

And the structural bit that makes it hold: **the instruction the model receives and the
parser that reads the reply live in the same file** — `PROMPT_RULE` and `find_verdict`
are both exported from `verdict_contract.py`. Two copies of a contract are one drift away
from failing silently. The `self-poisoning` case asserts the prompt itself parses as
nothing, so an echoed instruction is inert.

## Quickstart

```bash
git clone https://github.com/Palo-Alto-AI-Research-Lab/verdict-contract
cd verdict-contract
python3 test_verdict_contract.py        # 42 cases, exit 0
```

Gate any CLI reviewer you already use — the wiring is `examples/review_gate.py`:

```bash
git diff | python3 examples/review_gate.py 'codex exec --model gpt-5'
echo "exit $?"      # 0 approve / 3 blocked / 4 the model broke the contract
```

In your own code, both sides come from one import of `verdict_contract.py`:

```python
from verdict_contract import PROMPT_RULE, find_verdict, exit_code

prompt = MY_REVIEW_TASK + "\n\n" + PROMPT_RULE     # never retype the rule
report = my_model.run(prompt, diff)
sys.exit(exit_code(find_verdict(report)))
```

## What you are looking at

`verdict_contract.py` is the sanitized twin of a module that has gated every code review
across a 6-machine agent fleet since 2026-07-21, unchanged.

The test cases are not hypotheticals: each one is a counterexample a vendor model produced
while trying to break the fix, over seven adversarial rounds — the round-by-round record is
[devlog/2026-08-04-seven-rounds-to-a-verdict.md](devlog/2026-08-04-seven-rounds-to-a-verdict.md).
Four of those rounds found a real hole in code we already believed was correct.

Not included, on purpose: our reviewer prompts, machine topology, and approval routing.
The contract is the reusable part; what changed when is in `CHANGELOG.md`.

## Roadmap

**Now — [v0.1.0](https://github.com/Palo-Alto-AI-Research-Lab/verdict-contract/releases/tag/v0.1.0).**
`PROMPT_RULE` + strict/weak parser + `exit_code()` in one stdlib file, 42 contract cases, CI on
three OSes × three Pythons plus a weekly run so rot surfaces without a push.

**Next**, in the order we would take them:

- **More counterexamples.** This contract only knows the failures 42 cases have shown it. The most
  valuable thing anyone can send is a reviewer reply that fools it —
  [open an issue with the exact text](https://github.com/Palo-Alto-AI-Research-Lab/verdict-contract/issues).
- **Wrappers for more reviewers.** `examples/review_gate.py` wraps any CLI reviewer today; the
  common asks are a GitHub Action and a pre-commit hook.
- **Retiring the weak legacy layer.** It can block but never approve — deliberate, and it should
  stop being needed once callers emit the sentinel.

Every noticeable change ships as a new release, so the
[release feed](https://github.com/Palo-Alto-AI-Research-Lab/verdict-contract/releases) — not the
commit graph — is where you can see whether the contract has moved under you.

## Who made this

[Palo Alto AI Research Lab](https://github.com/Palo-Alto-AI-Research-Lab) — one founder
and an AI cofounder running a fleet of autonomous Claude machines, shipping the useful
pieces for free. How this repo expects a change to be proven, human or agent, is in `AGENTS.md`.

If this saves you one bad merge, **a star helps more than you would think** — we are looking
for the first ten people who actually run it. Found a case that breaks it? Open an issue at
https://github.com/Palo-Alto-AI-Research-Lab/verdict-contract/issues with the exact reply
text; a counterexample is the most valuable thing you can send us.

Related: [verified-ops-starter](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter)
(your job exited 0, prove it did the work) and
[awesome-verified-agents](https://github.com/Palo-Alto-AI-Research-Lab/awesome-verified-agents).

## Devlog

- [Seven rounds to a verdict](devlog/2026-08-04-seven-rounds-to-a-verdict.md) - how two vendor models spent an afternoon proving our review gate was lying, with every counterexample they produced.

---

<!--ecosystem-map:start-->

## 🧩 One piece of a working system

This repository is one piece lifted out of a live operation: one non-technical founder, an AI
cofounder, and a fleet of machines that reach consensus with each other and wake the human only
for money or the irreversible. It was extracted after it survived production, not written as a
demo — and it runs on its own: nothing here phones home to the rest.

**See how the whole thing fits together → [SYSTEM.md](https://github.com/Palo-Alto-AI-Research-Lab/Palo-Alto-AI-Research-Lab/blob/main/SYSTEM.md)**

Its closest neighbours in the **gates** layer: [`verbatim-citation-gate`](https://github.com/Palo-Alto-AI-Research-Lab/verbatim-citation-gate) · [`claim-check`](https://github.com/Palo-Alto-AI-Research-Lab/claim-check) · [`verified-ops-starter`](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter)

<!--ecosystem-map:end-->

## AI contributors

This project is built by a human + AI team, and the git log says so: Claude writes most of
the code, Codex and Grok review it, Gemini feeds the research. Each is credited on a commit
**only if its output changed that commit's content** — no decorative credits. Lab-wide
policy, one source for every repo: [AI-CONTRIBUTORS.md](https://github.com/Palo-Alto-AI-Research-Lab/.github/blob/main/AI-CONTRIBUTORS.md).
