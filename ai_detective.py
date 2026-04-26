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
# logic_utils.py — check_guess (hints are now correct)
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
        if g > secret:                           # lexicographic comparison — wrong for cross-digit sizes
            return "Too High", "📉 Go LOWER!"
        return "Too Low", "📈 Go HIGHER!"
""",
    "secret_type_switch": """\
# app.py — submit handler (type switch has been fixed)
secret = st.session_state.secret   # always an integer now
outcome, message = check_guess(guess_int, secret)
""",
    "get_range_for_difficulty": """\
# logic_utils.py — get_range_for_difficulty
def get_range_for_difficulty(difficulty: str):
    if difficulty == "Easy":   return 1, 20
    if difficulty == "Normal": return 1, 100
    if difficulty == "Hard":   return 1, 50
    return 1, 100

# app.py — info box now correctly uses {low} and {high} from get_range_for_difficulty
# so Easy shows 1-20, Normal shows 1-100, Hard shows 1-50. No range mismatch.
st.info(f"Guess a number between {low} and {high}. ...")
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

The game contains one known bug:
1. Score manipulation — on even-numbered attempts, a wrong "Too High" guess is
   rewarded with +5 points instead of penalised with -5 points.

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
