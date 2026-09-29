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

🚦 **Phase 1 — premise test** (gate: 4 Oct). Code written and unit-tested; running on real data.

## Timeline

| Phase | Dates | Owner | Status |
|---|---|---|---|
| 0 Setup: scaffold, read paper §5.1, roles, Drive, ask TA | 30 Sep – 1 Oct | all | 🟡 scaffold done |
| 1 Premise test (Dec-2024 week vs Jun-2025 week) | 1 – 4 Oct | A+B (C: EDA, backup topic) | 🟡 running |
| 📌 Submit topic + members | **5 Oct** | all | ⬜ |
| 2 Full pipeline Nov–Dec 2024 + May–Jun 2025 | 5 – 10 Oct | A, B, C | ⬜ |
| 3 Evaluation: vs paper Fig. 7 · synthetic injection · precision@k | 8 – 12 Oct | B (+C) | ⬜ |
| 4 Slides (14) · report (15) · video (16) · AI log | 10 – 16 Oct | all | ⬜ |
| 5 Buffer + Q&A prep | 17 – 18 Oct | all | ⬜ |
| 📌 Submit Video + PPT + Report | **19 Oct** | all | ⬜ |

Cut order if late: Oct-2025 window → Isolation Forest. Never cut: Algorithm 1 + evaluation.

## Premise test

Rule: **GO if Dec-2024 week flagged ≥ 30% and Jun-2025 week ≤ 10%** of share volume, at θ = 0.9.

- `04_Evaluation/premise_test/config.py` — windows, paper parameters, go rule
- `01_extract.py` — raw fills → one row per matched trade (A)
- `02_alg1.py` — closure flags (SQL) → x0 → iterate x = (x0 + Bx)/2 → flag (B)
- Results land in `04_Evaluation/premise_test/results/`

Run from `Project/`:
```bash
cd 04_Evaluation/premise_test
uv run python 01_extract.py
uv run python 02_alg1.py
```

### Decisions taken (don't silently reverse)
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

## Remaining
- [ ] Run premise test, record numbers here
- [ ] Ask TA: report length/language, video length, AI log, live presentation in week 14?
- [ ] C: EDA on the two weeks + one backup topic from `standout-da-finance-2569.md`
