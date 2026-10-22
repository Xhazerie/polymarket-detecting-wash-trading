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
| 6 | 2026-10-22 | B | Claude Code | "Review the code" (`/code-review` on the merged pipeline PR) | No correctness bugs; 6 edge-case/cleanup notes (empty-window division guard, non-convergence flag, uncreated temp dir, leaked DuckDB connection, duplicated month-stepping, redundant parquet scans). Logged for follow-up |
| 7 | 2026-10-22 | B | Claude Code | "Check the assignment template — what's left?" + "build synthetic injection + precision@k" | Gap-check vs `69_1_G_Assignment_#2_template-1.pdf` rubric; built `06_synthetic_injection.py` (plant known wash rings into the quiet window, measure recall@θ / precision@k / AP) and refactored `02_alg1.py` to share one `score_wallets()` |
| 8 | 2026-10-22 | B | Claude Code | "Save per-wallet flags (unblock EDA round 2)" | `07_wallet_flags.py` writes `results/wallet_flags/<window>.parquet` (per-wallet score, flag, target volume, wash volume, counterparties); logic verified on a synthetic smoke test |
| 9 | 2026-10-22 | C/B | Claude Code | "Build EDA round 2 (flagged vs unflagged)" + "add θ-sensitivity per market + Trump case study" | `03_Analytics/eda/eda_round2.ipynb` (score distribution, concentration, category/price, ring assortativity) and `08_market_theta.py` (per-market θ-curves → Trump false-positive verdict + figure); both verified runnable on synthetic data |
| 10 | 2026-10-22 | B | Claude Code | "Write the handoff + push to GitHub (exclude the assignment template PDF)" | Handoff doc written to a temp path; gitignored `69_1_G_Assignment_#2_template-1.pdf`; committed the new evaluation scripts + EDA round 2 + docs on a feature branch and pushed |
