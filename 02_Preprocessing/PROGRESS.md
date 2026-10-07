# Preprocessing progress

Updated: 7 October 2026

## Completed

- Ran the README workflow: baseline extraction, Algorithm 1 premise test, and EDA round 1.
- Downloaded October–December 2024 and April–June 2025 fills, plus condition and market metadata.
- Added `make_weekly_windows()` and `WEEKLY_WINDOWS` in `04_Evaluation/premise_test/config.py`.
- Updated `01_extract.py` to extract the original two baseline windows and 18 weekly windows covering November–December 2024 and May–June 2025.
- Each weekly window includes a 30-day lead-in and an `in_target` flag identifying trades in the target week. Weeks start on November 1 or May 1 and advance by seven days; the final window of each period is shorter.
- Reused the existing preprocessing: remove exchange-summary rows, lowercase addresses, convert amounts from six-decimal units, map tokens to markets and outcomes, and calculate maker position changes.

## Verified outputs

- Clean trade datasets: `data/interim/<window>_trades.parquet` (two baseline datasets and 18 weekly datasets).
- Extraction counts: `04_Evaluation/premise_test/results/extract_stats.json`.
- Across the 18 weekly target periods: **29,380,522 trades**, **0 unmapped-token rows**, and **0 self-trades** reported by extraction. Historical lead-in rows overlap across datasets and should not be summed as unique trades.
- Baseline Algorithm 1 results at threshold 0.9: **61.82%** of December 1–7, 2024 share volume flagged and **0.35%** of June 1–7, 2025 share volume flagged.
- EDA notebook: all 21 code cells executed, with no recorded error outputs.
- Weekly integrity validation: all 18 datasets passed `04_Evaluation/premise_test/03_validate.py`. Checks cover duplicate event IDs within each dataset, required fields, UTC date boundaries, target flags, finite positive share amounts, nonnegative USDC amounts, position-change magnitudes, lowercase addresses, self-trades, exchange-summary rows, and agreement with saved extraction counts and volume. Detailed results: `04_Evaluation/premise_test/results/weekly_validation.json`.
- Sampled position consistency: all 18 windows passed `04_validate_positions.py`, comparing cleaned maker/taker exposure against raw maker orders (including taker-summary rows). Checked 1,800 pair/window cases (523 distinct wallet-market pairs) and 13,613 block checkpoints, with zero differences. Details and limitations: `02_Preprocessing/POSITION_VALIDATION.md`; machine-readable results: `04_Evaluation/premise_test/results/position_validation.json`.

These checks confirm generated outputs and recorded counts; they do not establish that reconstructed positions or wash-trading flags are correct.

## Remaining

- Historical balance validation remains unresolved: the published `user_position` is an April 2026 state snapshot without historical timestamps, so it cannot be directly compared with 2024/2025 window endpoints. A compatible historical reference or full lifecycle reconstruction is required. The sampled raw-fill consistency check above is complete, but does not replace this validation.
- Test longer lead-in periods and measure their effect on positions and detection results.
- Have Algorithm 1 consume the weekly configurations and save weekly results and per-wallet scores/flags for evaluation and EDA round 2. The current algorithm still uses the two baseline windows.
- Prepare preprocessing slides and report content using the saved extraction counts and validation results.

The newer decisions in the root `PROGRESS.md` take precedence over the September 30 group-plan PDF: Algorithm 2 was dropped; planned evaluation includes threshold sensitivity, synthetic injection, and precision@k.
