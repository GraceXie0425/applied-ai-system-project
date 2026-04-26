# Model Card — Game Glitch Investigator: AI Bug Detective

> Standardized documentation for the AI component of this project,
> covering intended use, collaboration process, known limitations,
> misuse risks, and testing results.

---

## System Overview

**System name:** AI Bug Detective  
**Base model:** `claude-sonnet-4-6` via the Anthropic API  
**Integration type:** Agentic tool-use loop  
**Project:** Game Glitch Investigator (Applied AI System — Final)

The AI Bug Detective is a post-game analysis agent. After a player finishes a
session of the Game Glitch Investigator, the agent receives the full session
history (guesses, outcomes, hints shown, secret number, difficulty), drives a
multi-turn tool-use conversation with Claude, and produces a plain-language
report identifying which intentional bugs the player encountered and why the
code causes them.

---

## Intended Use

| Use case | Supported |
|----------|-----------|
| Explaining which game bugs a player encountered | Yes |
| Teaching players to read and reason about Python code | Yes |
| Automatically fixing bugs in source code | No |
| Analysing code outside this game's four known bug categories | Partially |
| Production bug detection on arbitrary codebases | No |

The system is designed for an educational context. Its primary audience is
students learning to identify and explain bugs, using the detective's report
as a model for how to trace from observed behavior back to code.

---

## AI Collaboration During Development

### Helpful instance

When designing the agentic loop in `ai_detective.py`, I asked Claude to
suggest the right pattern for driving a tool-use conversation with the
Anthropic API. It recommended a `while True` loop that checks
`response.stop_reason` on each turn — breaking on `"end_turn"` and continuing
on `"tool_use"` — rather than using recursion or a fixed iteration limit.

This was the correct pattern. I verified it against the Anthropic tool-use
documentation, which confirms `"tool_use"` as the signal that the model has
called a tool and is waiting for results, and `"end_turn"` as the signal that
the model is finished. Using explicit `stop_reason` checks also made the loop
easy to read and extend.

### Flawed instance

Early in the project I asked an AI assistant to help write tests for
`check_guess`. It generated:

```python
assert check_guess(50, 50) == "Win"
```

The actual function returns a tuple `("Win", "🎉 Correct!")`, not a bare
string, so this assertion would always fail. The AI inferred the return type
from the function name and docstring rather than from running the code, and
produced a syntactically valid but semantically wrong test.

The fix was straightforward — `outcome, _ = check_guess(50, 50)` — but the
episode reinforced an important habit: always run AI-generated tests immediately
and read the failure message carefully. A test that looks correct but asserts
the wrong thing is worse than no test, because it gives false confidence.

---

## Known Limitations and Biases

### 1. Stale source snippets

The four code sections the detective can inspect (`_CODE_SECTIONS` in
`ai_detective.py`) are hardcoded strings copied from the source at a point in
time. If `logic_utils.py` or `app.py` are edited, the detective's evidence
does not update automatically. It can report a bug as present when it has
already been fixed, or miss a new bug introduced after the snippets were
written.

**Severity:** High for any modified fork of the project. Low for the
unmodified original, where the snippets are accurate.

### 2. Confirmation framing

The system prompt tells the agent upfront that there are exactly four bug
categories and lists them by name. This primes the model to find those four
patterns. If a user introduces a fifth bug — or if a session triggers an edge
case not covered by the four categories — the detective may misattribute it to
a known category or ignore it entirely.

**Severity:** Medium. Mitigated by the fact that the game's bugs are fixed and
well-defined. Would become high in any open-ended version of the tool.

### 3. Non-deterministic depth

The detective's free-form markdown output varies in depth across runs on
identical inputs. One run may flag all four bugs with specific line-level
evidence; another may mention only two with brief descriptions. The tool-use
pattern (which sections get inspected) is more consistent than the final prose.

**Severity:** Low for a single-player educational tool. Would require a
structured JSON output schema if consistency were required (e.g., for automated
grading).

### 4. No ground-truth validation

Nothing in the system checks the detective's conclusions against a test run.
A wrong analysis looks identical to a correct one in the UI: structured
markdown, confident tone, specific attempt numbers cited. The player has no
in-app way to verify correctness beyond reading the source themselves.

---

## Misuse Risks and Mitigations

### Risk 1 — Homework shortcut

A student could submit the detective's bug report as their own analysis without
understanding the code. The report is detailed enough to pass a surface-level
review.

**Mitigation:** Add a Socratic follow-up in the UI that asks the player to
explain one bug back in their own words before the full report is revealed.
This turns the tool into a hint system rather than an answer key.

### Risk 2 — Over-trust in stale analysis

A user who has modified the game could receive a confident but wrong report,
spend time "fixing" a bug that was already fixed, or dismiss a real bug because
the detective did not flag it.

**Mitigation:** Display a clear disclaimer when the "Analyse" button is
clicked: *"This report is based on the original source. If you have modified
the code, verify the findings against your version."* Also show which sections
were inspected so the user can judge freshness.

### Risk 3 — Misapplied to other codebases

The detective's system prompt and code sections are specific to this game. If
a user passes in session data from a different application, the model will
attempt to map the evidence onto the four known bug categories, producing a
misleading report.

**Mitigation:** Scope the tool clearly in the UI ("This detective only knows
about the four bugs in this game"). Do not expose `run_detective()` as a
general-purpose API.

---

## Testing Results

### Automated tests

```
tests/test_game_logic.py::test_winning_guess   PASSED
tests/test_game_logic.py::test_guess_too_high  PASSED
tests/test_game_logic.py::test_guess_too_low   PASSED

3 passed in 0.01s
```

The tests import `logic_utils` directly, run without starting Streamlit,
and complete in under a second. Separating pure logic from the UI was the
key decision that made this possible.

### Manual AI output testing

Three hand-crafted sessions were run through the detective to validate output
quality:

| Session | Bugs expected | Bugs correctly identified |
|---------|---------------|--------------------------|
| Normal mode, hints followed — hit type confusion on attempt 2 | Type confusion, hint reversal | Both, with correct attempt numbers |
| Hard mode, guessed above 50 — hit range mismatch | Range mismatch, hint reversal | Both; detective quoted the `get_range_for_difficulty` snippet accurately |
| Even attempt with score reward — hit score manipulation | Score manipulation | Identified; correctly noted the `attempt_number % 2 == 0` condition |

### What surprised me

The detective handled the type-confusion bug better than expected. The bug only
produces a wrong result when the first digit of the guess differs from the
first digit of the secret (e.g., guessing 9 when the secret is 10). The model
correctly identified this specific condition — `"9" > "10"` is `True`
lexicographically — and gave a concrete counterexample without being prompted
to do so.

The biggest reliability gap was output consistency: running the same session
twice sometimes produced reports of different depth. One run would include
four fully evidenced bugs; another would merge two into a single paragraph.
For a graded or auditable system this would require switching to a
JSON-schema output format so completeness can be tested programmatically.

### What I learned

Keeping `logic_utils.py` as a pure-function module with no Streamlit imports
was the single most valuable structural decision. It meant tests could import
and run the logic in under a millisecond, without mocking session state or
spinning up a browser. The lesson: separate the logic you want to test from the
framework that renders it, even in a small project.

---

## Checklist

- [x] Model/system described and scoped
- [x] Intended use documented
- [x] AI collaboration: one helpful instance, one flawed instance
- [x] Limitations and biases identified with severity ratings
- [x] Misuse risks identified with concrete mitigations
- [x] Automated test results included
- [x] Manual AI output testing documented
- [x] Key lessons from testing recorded
