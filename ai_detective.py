"""
AI Bug Detective — inspects a completed game session and identifies bugs.

Primary path: agentic Claude API loop with tool use (requires API credits).
Fallback path: rule-based analysis that runs entirely in Python, no API needed.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source snippets the Claude agent can request as evidence
# ---------------------------------------------------------------------------
_CODE_SECTIONS = {
    "check_guess": """\
# logic_utils.py — check_guess (hints are correct)
def check_guess(guess, secret):
    if guess == secret:
        return "Win", "🎉 Correct!"
    try:
        if guess > secret:
            return "Too High", "📉 Go LOWER!"
        else:
            return "Too Low", "📈 Go HIGHER!"
    except TypeError:
        g = str(guess)
        if g == secret:
            return "Win", "🎉 Correct!"
        if g > secret:
            return "Too High", "📉 Go LOWER!"
        return "Too Low", "📈 Go HIGHER!"
""",
    "secret_type_switch": """\
# app.py — submit handler (type switch has been fixed)
secret = st.session_state.secret   # always an integer
outcome, message = check_guess(guess_int, secret)
""",
    "get_range_for_difficulty": """\
# logic_utils.py — get_range_for_difficulty
def get_range_for_difficulty(difficulty: str):
    if difficulty == "Easy":   return 1, 20
    if difficulty == "Normal": return 1, 100
    if difficulty == "Hard":   return 1, 50
    return 1, 100

# app.py — info box uses {low} and {high}, so the displayed range is correct.
""",
    "update_score": """\
# logic_utils.py — update_score
def update_score(current_score, outcome, attempt_number):
    if outcome == "Win":
        points = 100 - 10 * attempt_number
        return current_score + max(points, 10)
    if outcome == "Too High":
        if attempt_number % 2 == 0:
            return current_score + 5   # BUG: rewards a wrong guess on even attempts
        return current_score - 5
    if outcome == "Too Low":
        return current_score - 5
    return current_score
""",
}

_TOOLS = [
    {
        "name": "lookup_code_section",
        "description": (
            "Return the source code for a named section of the game. "
            "Use this to confirm or refute a hypothesis before writing your report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": list(_CODE_SECTIONS.keys()),
                    "description": (
                        "One of: check_guess, secret_type_switch, "
                        "get_range_for_difficulty, update_score"
                    ),
                }
            },
            "required": ["section"],
        },
    }
]

_SYSTEM = """\
You are a bug detective for a deliberately broken number-guessing game called
"Game Glitch Investigator". Your job is to examine a player's completed session
and produce a clear, evidence-based bug report.

The game contains one known bug:
1. Score manipulation — on even-numbered attempts, a wrong "Too High" guess is
   rewarded with +5 points instead of penalised with -5 points.

Process:
• Read the session data the user provides.
• Call lookup_code_section to inspect the update_score function.
• Build concrete evidence: quote the specific attempt number, the guess, the
  outcome received, and explain what the code does vs what it should do.
• Write a plain-language report. If the bug did not fire this session, say so.
• End with a one-sentence summary.
"""


# ---------------------------------------------------------------------------
# Rule-based fallback (no API required)
# ---------------------------------------------------------------------------
def _rule_based_report(session: dict) -> str:
    """
    Deterministic bug analysis that runs with no API or credits.
    Checks the session for the one remaining intentional bug: score manipulation.
    """
    attempts = session.get("attempts", [])
    difficulty = session.get("difficulty", "Normal")
    secret = session.get("secret", "?")
    result = session.get("final_result", "unknown")
    score = session.get("final_score", 0)

    triggered = [
        a for a in attempts
        if a.get("attempt", 0) % 2 == 0 and a.get("outcome") == "Too High"
    ]

    lines = [
        "## Bug Detective Report *(rule-based)*",
        "",
        f"**Session:** {difficulty} difficulty · secret `{secret}` · "
        f"result `{result}` · final score `{score}`",
        "",
        "---",
        "",
        "### Bug inspected: Score Manipulation (`update_score`)",
        "",
        "```python",
        "if outcome == 'Too High':",
        "    if attempt_number % 2 == 0:",
        "        return current_score + 5   # BUG: rewards a wrong guess",
        "    return current_score - 5",
        "```",
        "",
    ]

    if not triggered:
        lines += [
            "**Result: bug did not fire this session.**",
            "",
            "None of your wrong guesses landed on an even attempt number with "
            "outcome `Too High`, so the +5 reward condition was never reached. "
            "Your score was penalised correctly on every wrong guess.",
        ]
    else:
        lines += [
            f"**Result: bug fired {len(triggered)} time(s).**",
            "",
        ]
        for a in triggered:
            lines += [
                f"- **Attempt {a['attempt']}** — you guessed `{a['guess']}` "
                f"(outcome: *Too High*). "
                f"Because attempt {a['attempt']} is even, `update_score` added "
                f"**+5 points** instead of subtracting **-5 points**. "
                f"That is a 10-point swing in your favour for a wrong answer.",
            ]
        lines += [
            "",
            "The correct behaviour would penalise every wrong guess equally "
            "regardless of attempt parity.",
        ]

    lines += [
        "",
        "---",
        "",
        "*To run the full AI-powered analysis, add a valid `ANTHROPIC_API_KEY` "
        "to your `.env` file.*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_detective(session: dict) -> dict:
    """
    Analyse a completed game session.

    Tries the Claude agentic loop first. Falls back to the rule-based
    analyser if no API key is set or if credits are exhausted.

    Returns:
        analysis                — markdown report string
        code_sections_inspected — list of section names inspected
        session                 — original session dict
        mode                    — "ai" or "rule-based"
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        try:
            return _run_ai_detective(session, api_key)
        except Exception as exc:
            msg = str(exc).lower()
            if "credit" in msg or "401" in msg or "403" in msg or "400" in msg:
                logger.warning("API unavailable (%s); falling back to rule-based analysis.", exc)
            else:
                raise

    logger.info("No API key or credits — using rule-based detective.")
    return {
        "analysis": _rule_based_report(session),
        "code_sections_inspected": ["update_score"],
        "session": session,
        "mode": "rule-based",
    }


def _run_ai_detective(session: dict, api_key: str) -> dict:
    """Agentic Claude tool-use loop."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    sections_inspected: list[str] = []

    messages = [
        {
            "role": "user",
            "content": (
                "Please analyse this game session and report every bug the "
                "player encountered:\n\n"
                + json.dumps(session, indent=2)
            ),
        }
    ]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_SYSTEM,
            tools=_TOOLS,
            messages=messages,
        )
        logger.debug("Detective stop_reason=%s", response.stop_reason)

        if response.stop_reason == "end_turn":
            analysis = next(
                (b.text for b in response.content if hasattr(b, "text")),
                "No analysis produced.",
            )
            logger.info("AI detective finished. Sections: %s", sections_inspected)
            return {
                "analysis": analysis,
                "code_sections_inspected": sections_inspected,
                "session": session,
                "mode": "ai",
            }

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    section = block.input.get("section", "")
                    sections_inspected.append(section)
                    code = _CODE_SECTIONS.get(section, f"Unknown section: {section}")
                    logger.info("Detective inspecting: %s", section)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": code,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        logger.warning("Unexpected stop_reason: %s", response.stop_reason)
        break

    return {
        "analysis": "Investigation could not be completed.",
        "code_sections_inspected": sections_inspected,
        "session": session,
        "mode": "ai",
    }
