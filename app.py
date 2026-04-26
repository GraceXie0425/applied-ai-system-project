import json
import logging
import os
import random

import streamlit as st
from dotenv import load_dotenv

from logic_utils import (
    check_guess,
    get_range_for_difficulty,
    parse_guess,
    update_score,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Logging — every session is appended to sessions.log as a JSON line
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename="sessions.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _log_session(session: dict) -> None:
    logger.info("SESSION %s", json.dumps(session))


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Glitchy Guesser", page_icon="🎮")
st.title("🎮 Game Glitch Investigator")
st.caption("An AI-generated guessing game. Something is off.")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.header("Settings")
difficulty = st.sidebar.selectbox("Difficulty", ["Easy", "Normal", "Hard"], index=1)

attempt_limit_map = {"Easy": 6, "Normal": 8, "Hard": 5}
attempt_limit = attempt_limit_map[difficulty]
low, high = get_range_for_difficulty(difficulty)

st.sidebar.caption(f"Range: {low} to {high}")
st.sidebar.caption(f"Attempts allowed: {attempt_limit}")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "secret" not in st.session_state:
    st.session_state.secret = random.randint(low, high)
if "attempts" not in st.session_state:
    st.session_state.attempts = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "status" not in st.session_state:
    st.session_state.status = "playing"
if "history" not in st.session_state:
    st.session_state.history = []
if "attempt_log" not in st.session_state:
    # Structured log consumed by the AI detective
    st.session_state.attempt_log = []
if "detective_report" not in st.session_state:
    st.session_state.detective_report = None

# ---------------------------------------------------------------------------
# Game UI
# ---------------------------------------------------------------------------
st.subheader("Make a guess")
st.info(
    f"Guess a number between {low} and {high}. "
    f"Attempts left: {attempt_limit - st.session_state.attempts}"
)

with st.expander("Developer Debug Info"):
    st.write("Secret:", st.session_state.secret)
    st.write("Attempts:", st.session_state.attempts)
    st.write("Score:", st.session_state.score)
    st.write("Difficulty:", difficulty)
    st.write("History:", st.session_state.history)

raw_guess = st.text_input("Enter your guess:", key=f"guess_input_{difficulty}")

col1, col2, col3 = st.columns(3)
with col1:
    submit = st.button("Submit Guess 🚀")
with col2:
    new_game = st.button("New Game 🔁")
with col3:
    show_hint = st.checkbox("Show hint", value=True)

if new_game:
    for key in [
        "secret", "attempts", "score", "status",
        "history", "attempt_log", "detective_report",
    ]:
        st.session_state.pop(key, None)
    st.success("New game started.")
    st.rerun()

# ---------------------------------------------------------------------------
# Post-game panel (shown when game is over)
# ---------------------------------------------------------------------------
if st.session_state.status != "playing":
    if st.session_state.status == "won":
        st.success("You already won. Start a new game to play again.")
    else:
        st.error("Game over. Start a new game to try again.")

    st.divider()
    st.subheader("🔍 AI Bug Detective")
    st.caption(
        "The detective analyses your session, inspects the source code, "
        "and explains exactly which bugs you hit."
    )

    if st.button("Analyse My Session"):
        session_data = {
            "difficulty": difficulty,
            "secret": st.session_state.secret,
            "final_result": st.session_state.status,
            "final_score": st.session_state.score,
            "attempts": st.session_state.attempt_log,
        }
        _log_session(session_data)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to a .env file in this directory and restart the app."
            )
        else:
            with st.spinner("Investigating bugs…"):
                try:
                    from ai_detective import run_detective
                    report = run_detective(session_data)
                    st.session_state.detective_report = report
                except Exception as exc:
                    logger.error("Detective failed: %s", exc)
                    st.error(f"Investigation failed: {exc}")

    if st.session_state.detective_report:
        report = st.session_state.detective_report
        inspected = report.get("code_sections_inspected", [])
        if inspected:
            st.markdown(
                "**Code sections inspected:** " + ", ".join(f"`{s}`" for s in inspected)
            )
        st.markdown(report["analysis"])

    st.stop()

# ---------------------------------------------------------------------------
# Guess submission
# ---------------------------------------------------------------------------
if submit:
    st.session_state.attempts += 1
    ok, guess_int, err = parse_guess(raw_guess)

    if not ok:
        st.session_state.history.append(raw_guess)
        st.error(err)
    else:
        st.session_state.history.append(guess_int)

        # BUG: type switch — even attempts compare against a string secret
        if st.session_state.attempts % 2 == 0:
            secret = str(st.session_state.secret)
            secret_type = "string"
        else:
            secret = st.session_state.secret
            secret_type = "integer"

        outcome, message = check_guess(guess_int, secret)

        if show_hint:
            st.warning(message)

        st.session_state.score = update_score(
            current_score=st.session_state.score,
            outcome=outcome,
            attempt_number=st.session_state.attempts,
        )

        # Record structured attempt data for the AI detective
        st.session_state.attempt_log.append(
            {
                "attempt": st.session_state.attempts,
                "guess": guess_int,
                "outcome": outcome,
                "hint_shown": message,
                "secret_type_used": secret_type,
            }
        )

        if outcome == "Win":
            st.balloons()
            st.session_state.status = "won"
            st.success(
                f"You won! The secret was {st.session_state.secret}. "
                f"Final score: {st.session_state.score}"
            )
        elif st.session_state.attempts >= attempt_limit:
            st.session_state.status = "lost"
            st.error(
                f"Out of attempts! "
                f"The secret was {st.session_state.secret}. "
                f"Score: {st.session_state.score}"
            )

st.divider()
st.caption("Built by an AI that claims this code is production-ready.")
