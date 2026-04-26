"""
AI Bug Detective — agentic loop that inspects a completed game session and
identifies which of the game's known bugs the player encountered.

The agent is given tools to look up specific source-code sections. It calls
those tools as needed, reasons over the evidence, then writes a plain-language
bug report.
"""

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

# Relevant snippets of the game's buggy source code, keyed by section name.
# The detective uses these as evidence when building its report.
_CODE_SECTIONS = {
    "check_guess": """\
# logic_utils.py — check_guess
def check_guess(guess, secret):
    if guess == secret:
        return "Win", "🎉 Correct!"
    try:
        if guess > secret:
            return "Too High", "📈 Go HIGHER!"   # hint says HIGHER but guess was too HIGH → should say LOWER
        else:
            return "Too Low", "📉 Go LOWER!"    # hint says LOWER  but guess was too LOW  → should say HIGHER
    except TypeError:
        g = str(guess)
        if g == secret:
            return "Win", "🎉 Correct!"
        if g > secret:                           # lexicographic comparison — wrong for cross-digit sizes
            return "Too High", "📈 Go HIGHER!"
        return "Too Low", "📉 Go LOWER!"
""",
    "secret_type_switch": """\
# app.py — submit handler
if st.session_state.attempts % 2 == 0:
    secret = str(st.session_state.secret)   # even attempts: secret becomes a STRING
else:
    secret = st.session_state.secret        # odd  attempts: secret is an INT
outcome, message = check_guess(guess_int, secret)
# When secret is a string, int > str raises TypeError and falls into the
# lexicographic branch of check_guess, which gives wrong results for guesses
# whose first digit differs from the secret's first digit (e.g. 9 vs 10).
""",
    "get_range_for_difficulty": """\
# logic_utils.py — get_range_for_difficulty
def get_range_for_difficulty(difficulty: str):
    if difficulty == "Easy":   return 1, 20
    if difficulty == "Normal": return 1, 100
    if difficulty == "Hard":   return 1, 50   # actual range is 1–50
    return 1, 100

# app.py — info box (always shows the wrong range for Hard)
st.info(f"Guess a number between 1 and 100. ...")
""",
    "update_score": """\
# logic_utils.py — update_score
def update_score(current_score, outcome, attempt_number):
    if outcome == "Win":
        points = 100 - 10 * (attempt_number + 1)
        return current_score + max(points, 10)
    if outcome == "Too High":
        if attempt_number % 2 == 0:
            return current_score + 5   # BUG: rewards a wrong guess on even attempts
        return current_score - 5
    if outcome == "Too Low":
        return current_score - 5       # always penalises Too Low, never rewards
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

The game contains four categories of known bugs:
1. Hint reversal — hints tell the player to go in the wrong direction.
2. Type confusion — on even-numbered attempts the secret is cast to a string,
   causing lexicographic comparison instead of numeric comparison.
3. Range display mismatch — Hard difficulty actually uses 1–50 but the UI says 1–100.
4. Score manipulation — wrong guesses are sometimes rewarded on even attempts.

Process:
• Read the session data the user provides.
• For each bug you suspect, call lookup_code_section to examine the relevant code.
• Build concrete evidence: quote the specific attempt number, the guess, the
  outcome received, and what the correct outcome should have been.
• Write a final report that a non-programmer could understand, listing every bug
  that actually fired during this session (ignore bugs that did not fire).
• End with a one-sentence summary.
"""


def run_detective(session: dict) -> dict:
    """
    Run the agentic bug-detective loop on a completed game session.

    Returns a dict:
        analysis               — markdown bug report string
        code_sections_inspected — list of section names the agent looked up
        session                 — the original session dict
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to a .env file or export it in your shell."
        )

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
            logger.info(
                "Detective finished. Sections inspected: %s",
                sections_inspected,
            )
            return {
                "analysis": analysis,
                "code_sections_inspected": sections_inspected,
                "session": session,
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
    }
