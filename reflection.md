# 💭 Reflection: Game Glitch Investigator

Answer each question in 3 to 5 sentences. Be specific and honest about what actually happened while you worked. This is about your process, not trying to sound perfect.

## 1. What was broken when you started?

- What did the game look like the first time you ran it?
- List at least two concrete bugs you noticed at the start  
  (for example: "the hints were backwards").

---

## 2. How did you use AI as a teammate?

- Which AI tools did you use on this project (for example: ChatGPT, Gemini, Copilot)?
- Give one example of an AI suggestion that was correct (including what the AI suggested and how you verified the result).
- Give one example of an AI suggestion that was incorrect or misleading (including what the AI suggested and how you verified the result).

---

## 3. Debugging and testing your fixes

- How did you decide whether a bug was really fixed?
- Describe at least one test you ran (manual or using pytest)  
  and what it showed you about your code.
- Did AI help you design or understand any tests? How?

---

## 4. What did you learn about Streamlit and state?

- How would you explain Streamlit "reruns" and session state to a friend who has never used Streamlit?

---

## 5. Looking ahead: your developer habits

- What is one habit or strategy from this project that you want to reuse in future labs or projects?
  - This could be a testing habit, a prompting strategy, or a way you used Git.
- What is one thing you would do differently next time you work with AI on a coding task?
- In one or two sentences, describe how this project changed the way you think about AI generated code.

---

## 6. Responsible AI — Limitations, Bias, and Misuse

### What are the limitations or biases in your system?

The biggest limitation is that the detective's knowledge is frozen: the four `_CODE_SECTIONS` snippets in `ai_detective.py` are hardcoded strings, not live reads of the source file. If someone edits `logic_utils.py` to fix a bug, the detective will still "find" it because it is reading an outdated copy of the code. This creates a gap between what the AI says is broken and what is actually broken — a subtle but serious reliability problem.

There is also a framing bias baked into the system prompt. The detective is told upfront that there are exactly four bug categories and is instructed to look for them. This makes it very good at finding the expected bugs and potentially blind to any new ones introduced by future edits. A model primed to find four specific patterns will tend to find those four even when the real problem is something else entirely.

Finally, the system has no way to verify whether its own reasoning is correct. It inspects code snippets and draws conclusions, but nothing in the loop checks the conclusion against a ground-truth test run. The output feels authoritative — structured markdown, confident tone — but a wrong analysis would look identical to a correct one from the player's perspective.

---

### Could your AI be misused, and how would you prevent that?

The most direct misuse is using the detective as a homework shortcut: a student could feed it any broken code, get a plain-English explanation of the bugs, and submit that explanation without understanding anything. The system is designed to teach by explaining, which is genuinely useful, but explanation is not the same as understanding — and a student who reads the report without tracing the reasoning themselves learns little.

A more subtle misuse is over-trust. The detective sounds confident and specific (it quotes attempt numbers, guesses, and code lines), which can make a plausible-but-wrong report feel like proof. If a player is debugging their own modified version of the game and the detective's snippets are stale, they could spend time "fixing" a bug that was already fixed — or worse, dismiss a real bug because the detective did not flag it.

To reduce these risks in a real deployment I would add: (1) a disclaimer in the UI that the report is based on hardcoded snippets and should be verified against the actual source; (2) a "show your work" mode that lets the player see exactly which snippets Claude received, so they can judge freshness; and (3) a follow-up prompt that asks the player to explain the bug back in their own words before showing the full report, turning the tool into a Socratic helper rather than an answer key.

---

### What surprised you while testing your AI's reliability?

The most surprising thing was how well the detective handled the type-confusion bug — the one where even-numbered attempts compare an integer guess against a string secret. I expected the model to describe it vaguely ("there may be a type mismatch") because the bug only produces wrong results for a specific class of inputs (guesses whose first digit differs from the secret's first digit, e.g. guessing 9 when the secret is 10). Instead, the model correctly identified the lexicographic-vs-numeric distinction and gave a concrete counterexample unprompted.

What did not work as well was consistency across sessions. Running the detective twice on the same session sometimes produced reports with different levels of detail — one run would flag all four bugs with specific evidence, another would flag only two and mention the others briefly in passing. The tool-use pattern was consistent (it always called `lookup_code_section`), but the depth of the final write-up varied in ways that were hard to predict. This was a reminder that language models are not deterministic; if reliability matters, you need a structured output format (like a JSON schema) rather than free-form markdown, so you can test completeness programmatically.

---

### Collaboration with AI: one helpful moment and one flawed one

**Helpful:** When I asked Claude to help structure the agentic loop in `ai_detective.py`, it immediately suggested modeling the loop as `while True` with explicit checks on `stop_reason` — breaking on `"end_turn"` and continuing on `"tool_use"` — rather than recursion or a fixed iteration count. This was the right pattern. I verified it by reading the Anthropic documentation on tool use, which confirms that `stop_reason == "tool_use"` is the correct signal that the model wants to call a tool and `"end_turn"` means it is done. Using `stop_reason` explicitly also made the loop's exit condition readable to anyone unfamiliar with the API.

**Flawed:** Early in the project I asked an AI assistant to help write the test for `check_guess`. It generated `assert check_guess(50, 50) == "Win"` — testing the return value as a plain string. The actual function returns a tuple `("Win", "🎉 Correct!")`, so this test would always fail. The AI did not check what `check_guess` actually returns; it inferred the return type from the function name and wrote a test that matched its assumption rather than the real implementation. This is a common failure mode: AI tools are good at generating plausible-looking code but they reason from patterns, not from running the code. The fix was straightforward (`outcome, _ = check_guess(50, 50)`), but it reinforced the habit of always running generated tests immediately and reading the failure message carefully before trusting that a test is correct.
