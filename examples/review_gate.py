#!/usr/bin/env python3
"""Wrap ANY CLI code reviewer in the verdict contract, in ~40 lines.

The reviewer can be Codex, Claude Code, Grok, a local model, curl to an API --
anything that takes a prompt on stdin and writes a review to stdout. What this
example shows is the part people usually get wrong: the prompt side and the
parser side must come from the SAME module, and the verdict must reach the
process exit status.

Usage:
    git diff | python3 review_gate.py 'codex exec --model gpt-5'
    git diff | python3 review_gate.py 'claude -p'

Exit codes:
    0  APPROVE            -- no blocking issues, safe for automation to proceed
    3  REQUEST_CHANGES    -- blocking issues found
    4  AMBIGUOUS / none   -- the model broke the contract; a human must read it
    2  usage error
"""
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from verdict_contract import PROMPT_RULE, find_verdict, verdict_line, exit_code

TASK = (
    "You are reviewing a diff. Report only MED/HIGH issues: correctness bugs, "
    "security holes, data loss, silent failure. Be specific -- file, line, and "
    "the concrete input that breaks it. Do not report style.\n\n"
    # The contract instruction is IMPORTED, never retyped. Retyping it is how the
    # two sides drift apart, and a drifted contract fails silently.
    + PROMPT_RULE
)


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    diff = sys.stdin.read()
    if not diff.strip():
        # An empty diff is not a failed review: there was nothing to object to.
        print("empty diff - nothing to review")
        return 0

    prompt = TASK + "\n\n--- DIFF ---\n" + diff
    proc = subprocess.run(argv[1], shell=True, input=prompt,
                          capture_output=True, text=True)
    report = proc.stdout

    print(report)
    print("-" * 60)
    print(verdict_line(report))
    # The verdict, not the reviewer's own exit status, decides. A reviewer that
    # crashes after printing a blocking review still blocks; a reviewer that exits
    # 0 having said nothing useful does NOT pass.
    return exit_code(find_verdict(report))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
