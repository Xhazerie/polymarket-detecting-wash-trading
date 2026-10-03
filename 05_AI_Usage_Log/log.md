# AI Usage Log

Record every meaningful AI interaction as it happens (not afterwards). The brief for
Group Assignment #1 required ≥ 5 prompts; assumed the same here.

| # | Date | Who | Tool | Prompt (short) | What we used / changed / rejected |
|---|---|---|---|---|---|
| 1 | 2026-09-30 | | Claude Code | "Plan the data-mining project: what, how, when, until done, covering every requirement" | Timeline + rubric→owner table (`PROGRESS.md`) |
| 2 | 2026-09-30 | | Claude Code | "Time is tight — run the premise test for us" | Pipeline in `04_Evaluation/premise_test/`; closure logic unit-tested on 6 hand-made cases before trusting it |
| 3 | 2026-09-30 | | Claude Code | Premise test run | GO: Dec-2024 61.8 % vs Jun-2025 0.35 % flagged; flagged the Trump-inauguration market as a disagreement with the paper's Algorithm 2 |
| 4 | 2026-09-30 | | Claude Code | "Make a PDF work plan to present to the group" + "why is EDA last?" | `plan/group_plan.pdf`; EDA moved before pre-processing after we questioned the order |
| 5 | 2026-10-03 | C | Claude Code | "I got the EDA role — what do I need to do?" | EDA plan; Claude wrote notebook setup + sections 1–2 as worked examples, C writes 3–6. Found: 70 % of Dec target-week volume is in markets opened before the lead-in; "39 % unnamed" does not apply to our windows |
| 6 | 2026-10-03 | C | Claude Code | "Finish the project EDA and explain everything in the .ipynb, with an explanation for every cell" | Sections 3–6 completed + 3.3 (top-2 partner share) and 6c (lead-in coverage) added; Thai markdown before/after every code cell. Checked by asserts (wallet count, join volume, % sums). Found the Trump market opened inside the lead-in, which overturned our own earlier hypothesis |
