#!/usr/bin/env python3
"""The verdict CONTRACT test: structure, not shape-guessing.

Every case below is a counterexample that was reproduced live against a
shape-guessing parser, across seven rounds of adversarial review by two
independent vendor models. This test fails if any of them regresses.

Run:  python3 test_verdict_contract.py     (exit 0 = green)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verdict_contract as vc  # noqa: E402

A, R = "APPROVE", "REQUEST_CHANGES"
AMB = "AMBIGUOUS"


# --- strict sentinel: the contract itself, decoration-tolerant, whole-line only.
# These are appended as the FINAL line of a fake review (APPROVE is only valid there).
STRICT = [
    ("===VERDICT=== APPROVE", A),
    ("===VERDICT=== REQUEST_CHANGES", R),
    ("===VERDICT===APPROVE", A),                     # no space
    ("**===VERDICT=== APPROVE**", A),                # bolded by the model
    ("> ===VERDICT=== REQUEST_CHANGES", R),          # blockquoted
    ("=== VERDICT === approve", A),                  # spacing + case
    ("==VERDICT== REQUEST CHANGES", R),              # fewer '=', space in value
    ("===VERDICT=== REQUEST-CHANGES.", R),           # hyphen + trailing dot
]

# --- weak legacy layer: old-style prose verdicts, sentinel absent -----------------
# Blocking reads still block (safe direction) ...
WEAK_BLOCKS = [
    "VERDICT: REQUEST_CHANGES",
    "## VERDICT: REQUEST_CHANGES",                   # seen live from a real reviewer
    "## Verdict — REQUEST CHANGES",                  # em dash + case + space
    "- VERDICT: REQUEST_CHANGES",
    "VERDICT: `REQUEST_CHANGES`",                    # backticked value: a silent miss before
]
# ... but an approve stated only in loose prose NEVER approves -- it goes AMBIGUOUS.
# This kills the false-approve class ("Example output: ..." shipped as a real OK).
WEAK_APPROVES_TO_AMB = [
    "VERDICT: APPROVE",
    "**Verdict:** APPROVE",
    "> VERDICT: APPROVE",
    "verdict: approve",
    "Example output: VERDICT: APPROVE",              # vendor counterexample (false approve)
    "I almost wrote VERDICT: APPROVE but changed my mind.",
]

# --- explicit AMBIGUOUS: the model marked a verdict but broke the contract --------
AMBIGUOUS_CASES = [
    "===VERDICT=== REJECT",                          # value outside the enum
    "===VERDICT=== APPROVE_WITH_NITS",               # enum is closed, no suffixes
    "===VERDICT=== LGTM",
    "End with VERDICT: APPROVE or VERDICT: REQUEST_CHANGES",  # old-prompt echo: both weak
    "## VERDICT: APPROVE\n\nOn reflection: VERDICT: REQUEST_CHANGES\n",  # mixed prose
    # A valid APPROVE must not win over a broken sentinel: junk poisons every
    # approve, and junk DETECTION must be broader than value validation (a
    # malformed "REJECT!" still has to count as a sentinel).
    "===VERDICT=== APPROVE\n===VERDICT=== REJECT",
    "===VERDICT=== LGTM\n===VERDICT=== APPROVE",
    "===VERDICT=== REJECT!\n===VERDICT=== APPROVE",
    "===VERDICT=== REJECT!",
    "===VERDICT===",                                 # bare marker, no value
    # ... and APPROVE is only clean as ONE sentinel on the FINAL non-blank line:
    "===VERDICT=== APPROVE\nActually, this has a serious bug.",
    "Looking at the tests, e.g.\n===VERDICT=== APPROVE\n\nI still think this "
    "needs changes for the unknown-sentinel bug.",
    "===VERDICT=== APPROVE\n\n===VERDICT=== APPROVE",             # repeated
    # The strict layer reads RAW lines, so a fenced/quoted APPROVE with no clean
    # final sentinel is a broken contract (loud), never a silent nothing:
    "```\n===VERDICT=== APPROVE\n```\nI disagree with the quoted example.",
    "Example:\n```\n===VERDICT=== APPROVE\n(the model forgot the closing fence)",
]

# --- nothing verdict-like at all -> None (rendered LOUD) --------------------------
NONE_CASES = [
    "The VERDICT is below.",
    "- see the VERDICT line at the end",
    "I could not decide; no verdict given.",
    "I refuse to give a VERDICT\nAPPROVE would be wrong",   # the newline-glue bug
    "see VERDICT\nREQUEST_CHANGES later maybe",             # ditto, blocking side
    "===VERDICT=== <value>",                                # PROMPT_RULE echo is inert
    "```diff\n+VERDICT: REQUEST_CHANGES\n```\nThat diff line is fine.",   # cited diff
    "VERDICT: APPROVE_WITH_NITS",                    # weak layer: \b keeps suffixes out
]


def main():
    fails = []

    # --- 1. the four outcomes ------------------------------------------------------
    for raw, want in STRICT:
        got = vc.find_verdict("# Review\n\nsome findings\n\n" + raw + "\n")
        if got != want:
            fails.append("strict: %r -> %r, want %r" % (raw, got, want))
    for raw in WEAK_BLOCKS:
        got = vc.find_verdict("findings\n" + raw)
        if got != R:
            fails.append("weak-block: %r -> %r, want %r" % (raw, got, R))
    for raw in WEAK_APPROVES_TO_AMB:
        got = vc.find_verdict("findings\n" + raw)
        if got != AMB:
            fails.append("weak-approve: %r -> %r, want AMBIGUOUS (never approve weakly)"
                         % (raw, got))
    for raw in AMBIGUOUS_CASES:
        got = vc.find_verdict(raw)
        if got != AMB:
            fails.append("ambiguous: %r -> %r, want AMBIGUOUS" % (raw, got))
    for raw in NONE_CASES:
        got = vc.find_verdict(raw)
        if got is not None:
            fails.append("none: %r misread as %r" % (raw, got))

    # a sentinel beats stray weak matches in the same reply (echo + real verdict)
    both = "the old form was VERDICT: APPROVE\n...\n===VERDICT=== REQUEST_CHANGES"
    if vc.find_verdict(both) != R:
        fails.append("sentinel did not take precedence over weak prose")
    # blocking is safe from ANY position and outranks junk/contradiction
    # (the asymmetry is intentional: RC > junk > APPROVE)
    for raw in ("===VERDICT=== REQUEST_CHANGES\nActually it's fine.",
                "===VERDICT=== APPROVE\nwait, no.\n===VERDICT=== REQUEST_CHANGES",
                "===VERDICT=== REQUEST_CHANGES\n===VERDICT=== REJECT",
                "===VERDICT=== REJECT!\n===VERDICT=== REQUEST_CHANGES"):
        if vc.find_verdict(raw) != R:
            fails.append("RC did not win: %r" % raw)
    # LIVE regression: a reviewer quoted a bare ``` INSIDE a ```text block; a
    # fence-tracking strict layer desynced, saw the quoted APPROVE as visible and
    # swallowed the real final REQUEST_CHANGES -> live false approve. The strict
    # layer must read raw lines: the final blocking sentinel wins here, full stop.
    desync = ("1. finding about fences:\n\n   ```text\n   Here is the required format:\n"
              "   ```\n   ===VERDICT=== APPROVE\n   ```\n\nmore findings\n\n"
              "===VERDICT=== REQUEST_CHANGES")
    if vc.find_verdict(desync) != R:
        fails.append("fence desync flipped a real REQUEST_CHANGES (live case)")
    # trailing blank lines after a final APPROVE must not break the position rule
    if vc.find_verdict("review text\n===VERDICT=== APPROVE\n\n  \n") != A:
        fails.append("trailing blanks broke the final-line APPROVE")

    # --- 2. loud rendering + exit-code gate ----------------------------------------
    if "!!" not in vc.verdict_line("no verdict here"):
        fails.append("missing verdict rendered quietly (must be LOUD)")
    if "!!" not in vc.verdict_line("===VERDICT=== REJECT"):
        fails.append("AMBIGUOUS rendered quietly (must be LOUD)")
    if vc.verdict_line("x\n===VERDICT=== APPROVE") != "VERDICT: APPROVE":
        fails.append("clean approve rendered wrong")
    for v, want in ((A, 0), (R, 3), (AMB, 4), (None, 4), ("NOT_STATED", 4)):
        if vc.exit_code(v) != want:
            fails.append("exit_code(%r) != %d" % (v, want))

    # --- 3. the prompt side of the contract ----------------------------------------
    # Self-poisoning guard: our own instruction text must never parse as a verdict.
    if vc.find_verdict(vc.PROMPT_RULE) is not None:
        fails.append("PROMPT_RULE itself parses as a verdict (self-poisoning)")
    # Every shipped example must carry the shared rule rather than reinvent one.
    ex = os.path.join(HERE, "examples", "review_gate.py")
    src = open(ex, encoding="utf-8").read()
    if "PROMPT_RULE" not in src:
        fails.append("examples/review_gate.py does not use the shared PROMPT_RULE")
    if "find_verdict" not in src:
        fails.append("examples/review_gate.py does not use the shared parser")

    if fails:
        print("FAIL (%d):" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    n = len(STRICT) + len(WEAK_BLOCKS) + len(WEAK_APPROVES_TO_AMB) + \
        len(AMBIGUOUS_CASES) + len(NONE_CASES)
    print("OK - %d contract cases (strict/weak/ambiguous/none) plus precedence, "
          "fence-desync, self-poisoning, loud rendering and exit-code gate" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
