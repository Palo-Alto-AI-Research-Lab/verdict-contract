"""A structured verdict contract for LLM code reviewers: the INSTRUCTION the model
gets (PROMPT_RULE) and the PARSER that reads its reply live in this ONE file, so the
two sides of the contract cannot drift apart.

Stdlib only. No dependencies. Python 3.8+.

WHY: A SHAPE-GUESSING REGEX IS NOT A CONTRACT
---------------------------------------------
The usual approach asks a model for a SHAPE ("VERDICT: APPROVE") and then guesses
the content back with a decoration-tolerant regex. Two independent vendor reviews
of exactly that design produced these live counterexamples:

  - a docstring promised "no newline in the gap", but `\\s` includes `\\n`, so
    "I refuse to give a VERDICT\\nAPPROVE would be wrong" parsed as APPROVE;
  - "Example output: VERDICT: APPROVE" parsed as a real approve -- a false approve
    is the dangerous direction;
  - the prompt itself contained both literals, so a model echoing its own
    instructions parsed as a verdict (prompt self-poisoning);
  - a second call site kept a third, divergent parser, so "one copy" was a lie;
  - the verdict lived only in stdout, never in the exit code, so automation read
    "the review printed something" as "the review passed".

THE FIX IS STRUCTURAL, IN FOUR PARTS
------------------------------------
  1. STRUCTURED MARKER -- the model must emit `===VERDICT=== <value>` alone on its
     final line. The strict parser matches WHOLE LINES only, so prose can never
     glue into a verdict and a newline gap is impossible by construction.
  2. CLOSED ENUM + EXPLICIT AMBIGUOUS + POSITION ENFORCED -- the value must be
     APPROVE or REQUEST_CHANGES. A sentinel with any other value, contradicting
     sentinels, a repeated APPROVE, or an APPROVE that is not the final non-blank
     line all return AMBIGUOUS (loud), never a guess and never a silent fail-safe.
     REQUEST_CHANGES blocks from anywhere. The asymmetry is the whole point:
     a false block costs a re-read, a false approve ships a bug.
  3. WEAK LAYER NEVER APPROVES -- if the model drops the sentinel and writes an
     old-style "VERDICT: ..." in prose, a blocking verdict still blocks (safe
     direction) but an approving one degrades to AMBIGUOUS. The strict layer reads
     the RAW reply: fence detection is undecidable on nested/unbalanced fences and
     once flipped a real REQUEST_CHANGES into an APPROVE in production. Best-effort
     fence stripping feeds only the weak layer, which cannot approve anyway.
     PROMPT_RULE itself contains no parseable literal (the value is written as
     `<value>`), so an instruction echo parses as nothing.
  4. EXIT-CODE GATE -- exit_code() maps the verdict onto the process exit status
     (0 approve / 3 request-changes / 4 ambiguous-or-missing), so automation can no
     longer treat any output as a pass.

Fail LOUD stays: AMBIGUOUS and missing verdicts render with an explicit warning
marker, never as a normal-looking line.

Test: python3 test_verdict_contract.py
"""
import re

APPROVE = "APPROVE"
REQUEST_CHANGES = "REQUEST_CHANGES"
AMBIGUOUS = "AMBIGUOUS"

# The one instruction every engine embeds in its review prompt. The value is spelled
# `<value>` so this text contains NO line the strict parser could match -- an echoed
# instruction is inert (self-poisoning fix). Keep it that way: never write a full
# `===VERDICT=== APPROVE`-style line into any prompt.
PROMPT_RULE = (
    "CRITICAL OUTPUT CONTRACT: the VERY LAST line of your reply must be exactly\n"
    "  ===VERDICT=== <value>\n"
    "where <value> is one bare word: APPROVE (no blocking issues) or\n"
    "REQUEST_CHANGES (one or more MED/HIGH issues). No backticks, no bold, no\n"
    "brackets, nothing else on that line. State it exactly once, on that final\n"
    "line only -- do not repeat the marker anywhere else in your reply.\n"
)

# Strict layer, stage 1: DETECT the marker with ANY remainder. Detection must be
# broader than validation: if the value class were part of detection, a malformed
# junk value ("REJECT!") would not register as a sentinel at all and could no longer
# poison an approve next to it. Leading markdown decoration is tolerated (models
# bold and quote things); leading prose is not.
_SENTINEL_MARK = re.compile(r"^[\s#>*\-]*={2,}\s*VERDICT\s*={2,}(.*)$", re.IGNORECASE)
# Stage 2 (in find_verdict): strip benign decoration off the remainder and validate
# against the closed enum; anything else on a marker line is junk. The one exemption
# is PROMPT_RULE's own literal placeholder, so quoted instructions stay inert.
_PLACEHOLDER = "<value>"
_REST_DECOR = " \t:*`."

# Weak legacy layer, used ONLY when no sentinel line exists at all. Same line only:
# the gap class has no \n (that newline smuggling was the original bug). Trailing \b
# keeps APPROVE_WITH_NITS / REQUEST_CHANGES_PLEASE from matching.
_WEAK = re.compile(
    r"VERDICT\b[^\S\n]*[:=*#>|.`~\-–— \t]{0,16}?(APPROVE|REQUEST[ _\-]?CHANGES)\b",
    re.IGNORECASE,
)

# Fenced code blocks are quotes, not statements. Used ONLY by the weak layer (the
# strict layer reads raw lines -- see find_verdict) as a best-effort filter so a
# quoted diff does not trip a weak "VERDICT: ..." read.
_FENCE_EDGE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


def _strip_fences(text):
    """Drop fenced blocks with a line-by-line state machine, not a regex: a regex
    only removes CLOSED fences; here an unclosed fence swallows everything to EOF.
    Nested/unbalanced fences can still desync this -- which is exactly why only the
    never-approving weak layer consumes the result. Closing fence: same char, at
    least the opening length, bare on its line."""
    out, char, ln = [], None, 0
    for line in (text or "").splitlines():
        m = _FENCE_EDGE.match(line)
        if char is None:
            if m:
                char, ln = m.group(1)[0], len(m.group(1))
            else:
                out.append(line)
        elif m and m.group(1)[0] == char and len(m.group(1)) >= ln \
                and line.strip() == m.group(1):
            char = None
    return "\n".join(out)


def _norm(value):
    return re.sub(r"[ \-]+", "_", value.strip().upper())


def find_verdict(text):
    """-> APPROVE | REQUEST_CHANGES | AMBIGUOUS | None (None = nothing verdict-like).

    AMBIGUOUS means the model DID mark a verdict but broke the contract
    (contradicting sentinels, a value outside the enum, or an approve stated only
    in loose prose). Both AMBIGUOUS and None must block automation -- see exit_code().
    """
    # STRICT LAYER runs on the RAW reply, on purpose. Nested/unbalanced fences make
    # "is this line inside a fence?" undecidable. Caught in production: a reviewer
    # quoted a bare ``` inside a ```text block, the fence tracker flipped, a quoted
    # APPROVE became "visible" and the real final REQUEST_CHANGES got swallowed ->
    # live false approve. So the strict layer never depends on fence detection:
    # REQUEST_CHANGES blocks from ANY line (even a quote -- a false block costs a
    # re-read), and APPROVE is accepted only in exactly the shape PROMPT_RULE
    # demands: the ONLY sentinel in the reply, on the final non-blank RAW line.
    # A quoted sentinel elsewhere can then at worst block or go AMBIGUOUS, never
    # approve.
    raw_lines = (text or "").splitlines()
    sentinels = []                  # (line index, normalized value or None if junk)
    last_nonblank = -1
    for i, line in enumerate(raw_lines):
        if line.strip():
            last_nonblank = i
        m = _SENTINEL_MARK.match(line)
        if m:
            rest = m.group(1).strip(_REST_DECOR)
            if rest == _PLACEHOLDER:
                continue            # PROMPT_RULE's own format line, quoted verbatim
            v = _norm(rest)
            sentinels.append((i, v if v in (APPROVE, REQUEST_CHANGES) else None))
    if sentinels:
        values = [v for _, v in sentinels]
        # Precedence: RC > junk > APPROVE. A blocking sentinel wins outright (even
        # next to junk or a contradicting APPROVE -- a real blocking review that
        # merely QUOTES a bad example must still read as blocking; seen live).
        # Junk then poisons any approve. APPROVE itself must be the only sentinel,
        # on the final line.
        if REQUEST_CHANGES in values:
            return REQUEST_CHANGES
        if any(v is None for v in values):
            return AMBIGUOUS        # sentinel with a value outside the enum
        if len(sentinels) == 1 and sentinels[0][0] == last_nonblank:
            return APPROVE
        return AMBIGUOUS            # repeated / not final -> not a clean approve
    # No sentinel anywhere -> weak legacy layer (old-style "VERDICT: ..." prose).
    # Fence stripping is BEST-EFFORT and only feeds this layer: it keeps a quoted
    # diff from tripping a weak read; if it misjudges, the weak layer still cannot
    # approve -- worst case is a false block or AMBIGUOUS, never a false OK.
    found = {_norm(m.group(1)) for m in _WEAK.finditer(_strip_fences(text))}
    if len(found) > 1:
        return AMBIGUOUS
    if REQUEST_CHANGES in found:
        return REQUEST_CHANGES      # blocking on a weak read is the safe direction
    if APPROVE in found:
        return AMBIGUOUS            # approving on a weak read never is
    return None


def verdict_line(text):
    """One printable line for the operator. Anything but a clean verdict is LOUD."""
    v = find_verdict(text)
    if v in (APPROVE, REQUEST_CHANGES):
        return "VERDICT: " + v
    if v == AMBIGUOUS:
        return ("VERDICT: AMBIGUOUS !!  <- the verdict contract was broken or "
                "self-contradictory; read the report yourself")
    return ("VERDICT: (not stated) !!  <- the model wrote no verdict; read the "
            "report yourself")


def exit_code(verdict):
    """Map a find_verdict() result onto the process exit status.

    0 = APPROVE, 3 = REQUEST_CHANGES, 4 = AMBIGUOUS or not stated.
    1/2 stay free for generic script/usage errors. Callers that only need
    "did the review pass" can simply test for exit 0.
    """
    return {APPROVE: 0, REQUEST_CHANGES: 3}.get(verdict, 4)
