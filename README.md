# verdict-contract

**Your LLM reviewer said APPROVE. Did it?**

If you pipe a diff to a model and grep its reply for `VERDICT: APPROVE`, you do not
have a gate. You have a coin flip that fails in the dangerous direction. This repo is
the ~190-line stdlib-only module that replaced ours, plus the 42 counterexamples that
forced every line of it.

MIT. No dependencies. Python 3.8+. Copy one file and go.

---

## The failure it fixes

We ran a real two-vendor review gate over our own diffs. Then we asked the two
vendors to review the gate itself. Both independently answered `ROOT-FIXED: NO` and
reproduced these live:

| what the model wrote | what the old parser read | why it matters |
|---|---|---|
| `I refuse to give a VERDICT`<br>`APPROVE would be wrong` | APPROVE | `\s` in the gap class quietly includes `\n` |
| `Example output: VERDICT: APPROVE` | APPROVE | a quoted example shipped as a real pass |
| the prompt text itself, echoed back | APPROVE | the instruction contained both literals: prompt self-poisoning |
| `## VERDICT: REQUEST_CHANGES` | *(nothing)* | a silent miss: review happened, no verdict recorded, nobody shouting |
| a blocking review, printed then exit 0 | "the review passed" | the verdict never reached the exit code |

The last one is the whole category. A gate whose verdict lives only in stdout is not
a gate, it is a log line.

And one that only shows up in production: a reviewer quoted a bare ` ``` ` **inside**
a ` ```text ` block. Our fence tracker desynced, a quoted APPROVE became "visible",
the real final `REQUEST_CHANGES` got swallowed, and the gate approved a diff the
reviewer had just rejected. Fence detection is undecidable on nested or unbalanced
fences. So the strict layer here does not use it at all.

## The fix, in four parts

1. **Structured marker.** The model must emit `===VERDICT=== <value>` alone on its
   final line. The parser matches whole lines only, so prose can never glue into a
   verdict and a newline gap is impossible by construction.
2. **Closed enum, explicit AMBIGUOUS, position enforced.** `APPROVE` or
   `REQUEST_CHANGES`, nothing else. A junk value, contradicting markers, a repeated
   marker, or an APPROVE that is not the final non-blank line all return `AMBIGUOUS`
   loudly. Never a guess, never a silent fail-safe.
3. **The weak layer can block but never approve.** Old-style prose verdicts still
   block (safe direction); a prose approve degrades to `AMBIGUOUS`. **The asymmetry is
   the design**: a false block costs a re-read, a false approve ships a bug.
4. **Exit-code gate.** `0` approve, `3` request-changes, `4` ambiguous or missing.
   Automation can no longer read "it printed something" as "it passed".

And the structural bit that makes it hold: **the instruction the model receives and
the parser that reads the reply live in the same file.** Two copies of a contract are
one drift away from failing silently. The test asserts the prompt itself parses as
nothing, so an echoed instruction is inert.

## Quickstart

```bash
git clone https://github.com/Palo-Alto-AI-Research-Lab/verdict-contract
cd verdict-contract
python3 test_verdict_contract.py        # 42 cases, exit 0
```

Gate any CLI reviewer you already use:

```bash
git diff | python3 examples/review_gate.py 'codex exec --model gpt-5'
echo "exit $?"      # 0 approve / 3 blocked / 4 the model broke the contract
```

In your own code, both sides come from one import:

```python
from verdict_contract import PROMPT_RULE, find_verdict, exit_code

prompt = MY_REVIEW_TASK + "\n\n" + PROMPT_RULE     # never retype the rule
report = my_model.run(prompt, diff)
sys.exit(exit_code(find_verdict(report)))
```

## What you are looking at

`verdict_contract.py` is the sanitized twin of a module that has gated every code
review across a 6-machine agent fleet since 2026-07-21, unchanged. The test cases are
not hypotheticals: each one is a counterexample a vendor model produced while trying
to break the fix, over seven adversarial rounds. Four of those rounds found a real
hole in code we already believed was correct.

Not included, on purpose: our reviewer prompts, machine topology, and approval
routing. The contract is the reusable part.

## Who made this

[Palo Alto AI Research Lab](https://github.com/Palo-Alto-AI-Research-Lab) - one
founder and an AI cofounder running a fleet of autonomous Claude machines, shipping
the useful pieces for free.

If this saves you one bad merge, **a star helps more than you would think** - we are
looking for the first ten people who actually run it. Found a case that breaks it?
Open an issue with the exact reply text; a counterexample is the most valuable thing
you can send us.

Related: [verified-ops-starter](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter)
(your job exited 0, prove it did the work) and
[awesome-verified-agents](https://github.com/Palo-Alto-AI-Research-Lab/awesome-verified-agents).

## Devlog

- [Seven rounds to a verdict](devlog/2026-08-04-seven-rounds-to-a-verdict.md) - how two vendor models spent an afternoon proving our review gate was lying, with every counterexample they produced.
