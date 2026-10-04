# PROGRESS — 01204465 Assignment #2 "Analytics on Complex Data"

**Topic (to submit 5 Oct):** ตรวจจับการซื้อขายสมรู้ร่วมคิด (wash trading) และการโอนมูลค่าแฝง
(chip dumping) บน Polymarket
**Group:** 3 people, roles A (data pipeline) · B (Algorithm 1 + evaluation) · C (EDA + chip-dumping angle)
**Deadlines:** topic + members **Mon 5 Oct 2026** · Video + PPT + Report **Mon 19 Oct 2026**
**Deliverable format (assumed = Group Assignment #1, ⚠️ confirm with TA):** report 10–15 pp ·
video 8–15 min · Drive folder `GroupXX_ProjectName/` · AI Usage Log ≥ 5 prompts

Background: `research_labs/output/feasible-polymarket-wash-trading.md` (go verdict, 28 Sep)
Full plan: `~/.claude/plans/project-data-mining-nested-truffle.md`

## Current stage

✅ **Premise test PASSED on 30 Sep** (4 days early) → submit this topic on 5 Oct.
✅ **EDA round 1 done on 3 Oct** (`03_Analytics/eda/`, findings → A/B in `findings.md`).
Next: A extends the pipeline (lead-in → 6 months suggested) to full windows; B runs θ-sensitivity + synthetic injection
and saves per-wallet flags; C does EDA round 2 (flagged vs unflagged) by 10 Oct.

## Timeline

| Phase | Dates | Owner | Status |
|---|---|---|---|
| 0 Setup: scaffold, read paper §5.1, roles, Drive, ask TA | 30 Sep – 1 Oct | all | 🟡 scaffold done |
| 1 Premise test (Dec-2024 week vs Jun-2025 week) | 1 – 4 Oct | whole group (joint work) | ✅ passed 30 Sep |
| 📌 Submit topic + members | **5 Oct** | all | ⬜ |
| 2 Full pipeline Nov–Dec 2024 + May–Jun 2025 | 5 – 10 Oct | A, B, C | ⬜ |
| 3 Evaluation: θ-sensitivity · synthetic injection · precision@k | 8 – 12 Oct | B (+C) | ⬜ |
| 4 Slides (14) · report (15) · video (16) · AI log | 10 – 16 Oct | all | ⬜ |
| 5 Buffer + Q&A prep | 17 – 18 Oct | all | ⬜ |
| 📌 Submit Video + PPT + Report | **19 Oct** | all | ⬜ |

Cut order if late: Oct-2025 window → Isolation Forest. Never cut: Algorithm 1 + evaluation.
(Algorithm 2 dropped on 4 Oct — see the Framing decision.)

## Premise test

Rule: **GO if Dec-2024 week flagged ≥ 30% and Jun-2025 week ≤ 10%** of share volume, at θ = 0.9.

- `04_Evaluation/premise_test/config.py` — windows, paper parameters, go rule
- `01_extract.py` — raw fills → one row per matched trade (role A takes over in phase 2)
- `02_alg1.py` — closure flags (SQL) → x0 → iterate x = (x0 + Bx)/2 → flag (role B takes over in phase 2)
- Results land in `04_Evaluation/premise_test/results/`

Run from `Project/`:
```bash
cd 04_Evaluation/premise_test
uv run python 01_extract.py
uv run python 02_alg1.py
```

### Result (30 Sep) — ✅ GO

| | Dec 1–7 2024 (peak) | Jun 1–7 2025 (quiet) |
|---|---|---|
| matched trades kept (lead-in + week) | 9,345,954 | 6,194,635 |
| taker-summary rows dropped | 7,867,942 | 4,359,293 |
| unmapped tokens / self-trades | 0 / 0 | 0 / 0 |
| target-week share volume | 692.9 M | 389.8 M |
| wallets | 334,362 | 295,526 |
| iterations to converge (paper: 12) | 10 | 11 |
| vol-weighted score x0 → final (must be equal, paper Prop. 2) | 0.7877 → 0.7877 | 0.5848 → 0.5848 |
| **flagged at θ = 0.9** | **61.8 %** (paper ≈ 60 %) | **0.35 %** (paper < 5 %) |
| θ = 0.7 / 0.8 / 0.95 / 0.99 | 76.5 / 70.9 / 59.8 / 55.1 % | 20.5 / 6.9 / 0.16 / 0.12 % |

- Wash is spread over 659 of 2,307 markets; the largest single market is 7.2 % of flagged
  volume. Top markets are sports long-shots (e.g. Blackhawks Stanley Cup 100 % flagged) →
  `results/dec2024_top_wash_markets.csv`.
- ⚠️ **"Will Donald Trump be inaugurated?" is 89 % flagged** by our fixed-θ run, but the paper's
  Algorithm 2 flags *nothing* there (no θ passes its spillover test). Likely fixed θ vs
  market-specific θ (EDA 3 Oct: the market opened inside our lead-in, so the lead-in is *not* the cause) →
  report it as a **false-positive case study** (θ-sensitivity + manual check), not as a paper mismatch.
- Runtime: ~15 s for both windows on 32 threads (DuckDB window functions, no Python loops).

### Decisions taken (don't silently reverse)
- **Framing (4 Oct): our own analysis, NOT a replication of the paper.** Comparing ourselves to
  Sirolly et al. made every difference look like a weakness. From now to the final report/slides/video:
  cite the paper **once** as the source of Algorithm 1 (+ why we picked the two windows) and at most
  **once** in validation ("in line with previously reported levels"). No side-by-side tables, no
  "paper: X" annotations, no "we haven't done Algorithm 2". Fixed θ is a design choice, backed by our
  own θ-sensitivity (0.7–0.99). **Algorithm 2 is dropped.** The Trump market = false-positive case study.
  The paper must still be cited — dropping the citation would be plagiarism.
- **Spec source:** paper PDF (public copy, gamblingharm.org), §5.1 Algorithm 1 and §6.
  Volume = **share** volume; buy/buy of N Yes + N No counts N, not 2N.
- **Only maker-fill rows are trades.** Rows whose `taker` is an exchange contract
  (`0x4bfb…` CTF, `0xc5d5…` NegRisk) are the taker order's summary → dropped.
- **Taker ΔP = −maker ΔP** in every match type (buy/sell, mint, merge), so the
  taker's side never has to be rebuilt.
- **Closure = existence test only** (Q > 0): any reversal, or a terminal contraction
  down to ≤ 0.5% of the running max. Checked on 6 hand-made cases (all pass).
- **Lead-in of one month** before each target week, for positions and scores.
  Positions opened before the lead-in are unknown → documented limitation.
- Raw files are downloaded once to `data/raw/` (gitignored); timestamps are strings,
  so querying over HTTP can't skip row groups by date.

## Group plan document (30 Sep)
- `plan/group_plan.pdf` (25 pp, Thai) — plan + content + premise-test results, for the group meeting
  before the 5 Oct topic submission. Charts come from `plan/make_figures.py` (reads `premise_test/results/`).
- Rebuild: `uv run python plan/make_figures.py` then
  `cd plan && latexmk -xelatex -outdir=build group_plan.tex && cp build/group_plan.pdf .`
- `plan/meeting_agenda.md` — short agenda (data state · roles · method) with the decisions to make.
- After the meeting: fill in the A/B/C names (§16) and TA's answers (§4), then rebuild.

## Remaining
- [ ] Ask TA: report length/language, video length, AI log, live presentation in week 14?
- [ ] C: EDA round 1 on the two weeks in `data/interim/` → findings to A/B by **4 Oct**;
      round 2 on the full range + flagged vs unflagged wallets by **10 Oct** (backup topic no longer needed)
      - ✅ 3 Oct: **EDA round 1 complete** — `03_Analytics/eda/eda_round1.ipynb` (60 cells, every code cell has
        Thai explanation before + interpretation after; runs clean in < 1 min), 6 figures in `eda/figures/`,
        72 numbers in `eda_stats.json`, full write-up for A/B in `eda/findings.md`. Key results (Dec vs Jun):
        - vol from wallets with top-2 partner share ≥ 0.9: **38.2 % vs 2.7 %**; top-1 share ≥ 0.8: 19.5 % vs 1.5 %;
          7,036 Dec wallets split ~50/50 between two partners (chain/ring pattern) → spot-check set for B
        - Sports **57 % vs 16 %** of volume (keyword categories, Other 3.7 % / 5.6 %)
        - volume at price < 0.02: **62.6 % vs 25.2 %**; 72,855 trades of exactly 96 shares at ~0.99 (Jun: 463)
        - lead-in coverage: 1 m 30 % → 3 m 66 % → **6 m 96 %** of Dec volume with full market history → A: extend lead-in
        - ⚠️ **Trump-inauguration market opened 1 Nov 22:45 UTC, inside the lead-in** → its 89 % flag is *not*
          a window-edge artefact → false-positive case study (θ-sensitivity + manual check)
      - 4 Oct: `eda/eda_facts.md` — facts + numbers only (no recommendations) for the group to understand the data
      - Round 2 (10 Oct) needs per-wallet/per-trade flags saved by B (results/ is market-level only)
- [ ] B: θ-sensitivity per market (Trump market as a false-positive case study) · synthetic injection · precision@k
      · save per-wallet flags (Algorithm 2 dropped 4 Oct — see Framing decision)
- [ ] A: extend to full Nov–Dec 2024 + May–Jun 2025 weekly series; sanity-check positions vs `user_position`
