# Lead-in sensitivity experiment

## Purpose

Measure how changing the available history affects wallet scores and flagged
share volume for the same two target weeks. This experiment changes both position
closure evidence and the counterparty network. It does not establish historical
token balances or provide ground truth for wash trading.

## Fixed settings

- Target weeks: December 1–7, 2024 and June 1–7, 2025 (UTC).
- Algorithm 1: reuse `02_alg1.py`, with threshold 0.9, closure parameter 0.005,
  and relative convergence tolerance 1e-5.
- History lengths: 30, 90, and 180 days, measured as exact day counts.
- Each experiment includes only its history and target week, with the target-end
  boundary exclusive.

| Period | Lead-in days | History starts | Target interval |
|---|---:|---|---|
| December 2024 | 30 | 2024-11-01 | [2024-12-01, 2024-12-08) |
| December 2024 | 90 | 2024-09-02 | [2024-12-01, 2024-12-08) |
| December 2024 | 180 | 2024-06-04 | [2024-12-01, 2024-12-08) |
| June 2025 | 30 | 2025-05-02 | [2025-06-01, 2025-06-08) |
| June 2025 | 90 | 2025-03-03 | [2025-06-01, 2025-06-08) |
| June 2025 | 180 | 2024-12-03 | [2025-06-01, 2025-06-08) |

The June baseline in `WINDOWS` starts on May 1 (31 days). The exact 30-day
experiment starts on May 2, so a small difference from the baseline is expected.

## Current results

The following runs completed on October 8, 2026:

| Period | Lead-in days | Target trades | Flagged share volume at threshold 0.9 | Market-history coverage proxy |
|---|---:|---:|---:|---:|
| December 2024 | 30 | 1,635,178 | 61.82% | 30.3% |
| December 2024 | 90 | 1,635,178 | 61.82% | 66.2% |
| December 2024 | 180 | 1,635,178 | 61.64% | 96.2% |
| June 2025 | 30 | 1,147,205 | 0.34% | 47.1% |
| June 2025 | 90 | 1,147,205 | 0.30% | 78.2% |
| June 2025 | 180 | 1,147,205 | 0.38% | 87.9% |

Coverage is the fraction of target share volume in markets whose metadata start
date falls within the available history. It is a proxy, not proof of complete
on-chain history. All six runs save this diagnostic in their per-run reports.
June has 20 target markets without a usable metadata start date, accounting for
0.051% of target share volume; they are not counted as covered.

December's target rows were identical across all three histories. Between 30 and
180 days, the flagged-volume total decreased by 0.1801 percentage points, but
16,687 of 104,186 target wallets (16.02%) crossed the threshold and 42,782 trade
flags changed. Those changed flags represent 0.7033% of target share volume.
Between 90 and 180 days, 2,419 wallets (2.32%) crossed the threshold and the mean
absolute score change was 0.01444. Similar aggregate fractions therefore do not
mean that the flagged-wallet populations are identical.

June's target rows were also identical across histories. Between 30 and 180 days,
the flagged-volume total increased by 0.0345 percentage points, while 10,939 of
87,130 target wallets (12.55%) crossed the threshold. The mean absolute score
change was 0.18148. Between 90 and 180 days, 10,059 wallets (11.54%) crossed the
threshold and the mean absolute score change was 0.10692. June's wallet scores
have not stabilized merely because its aggregate flagged volume remains low.

| Period | Days compared | Flagged-volume change (percentage points) | Volume whose trade flag changed | Wallet threshold crossings |
|---|---|---:|---:|---:|
| December | 30 -> 90 | -0.0016 | 0.5366% | 15.61% |
| December | 90 -> 180 | -0.1785 | 0.2459% | 2.32% |
| December | 30 -> 180 | -0.1801 | 0.7033% | 16.02% |
| June | 30 -> 90 | -0.0403 | 0.0591% | 4.29% |
| June | 90 -> 180 | +0.0748 | 0.0837% | 11.54% |
| June | 30 -> 180 | +0.0345 | 0.0976% | 12.55% |

Wallet percentages count all target wallets; a wallet crossing the threshold
does not automatically change all its trade flags because both counterparties
must meet the threshold. Volume with changed flags includes changes in either
direction, whereas the percentage-point difference is the net aggregate change.

## Interpretation and working recommendation

The high-versus-low flagged-volume contrast persists at all tested lengths.
Across the three lengths, December ranges from 61.64% to 61.82%, and June from
0.30% to 0.38%. This supports the period-level contrast under the tested setup.
It does not imply stable wallet identities, complete positions, or confirmed wash
trades. Extending history changes the score's historical trading context as well
as closure evidence.

A 180-day history is a reasonable working choice for these two target weeks if
the priority is broader market-history coverage: coverage rises to 96.2% and
87.9%. This is not a claim that 180-day scores are more accurate. Keep the shorter
runs as sensitivity evidence and prioritize wallets whose flags change for manual
evaluation. Applying 180 days to all weekly windows is a separate pipeline change;
the earliest November window would additionally need May 2024 fills.

## Verification

- All seven additional monthly files downloaded and their Parquet metadata was readable.
- All six Algorithm 1 runs converged in 10–13 iterations.
- No unmapped-token rows or self-trades were reported in these extractions.
- The volume-weighted initial and final score means agree at the saved precision.
- All six pairwise comparisons verified identical target rows and target-wallet
  populations before computing score/flag differences.

## Comparisons produced by the script

For each period, compare 30 versus 90, 90 versus 180, and 30 versus 180 days:

- Assert that target trade rows and wallet populations are identical.
- Measure mean and maximum absolute wallet-score changes.
- Count wallets crossing the fixed score threshold.
- Measure the share volume of target trades whose flags change.
- Report the flagged-volume difference in percentage points.

If results stabilize with more history, that supports a lead-in choice for these
two weeks. If they continue changing materially, report sensitivity and consider
more history or a market-history coverage restriction; do not call one run ground truth.

## Reproduce

From the repository root:

```bash
# Inspect windows and missing monthly files.
uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --plan

# Download missing months with resumable transfers (three concurrent files).
uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --download-only

# Run the six experiments and compare scores/flags.
uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py
```

Run just the available 30-day cases:

```bash
uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --days 30
```

Periods can also be run independently as their data becomes available:

```bash
uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --periods dec2024
uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --periods jun2025

# Combine and compare saved per-run results after all six runs complete.
uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --compare-only
```

Use `.venv/bin/python` in place of `uv run python` if `uv` is not on PATH and
the project virtual environment is already installed.

## Outputs

- Experiment trades: `data/interim/<period>_lead<days>_trades.parquet`.
- Target-wallet scores: `data/interim/lead_in_scores/<period>_lead<days>.parquet`.
- Extraction counts, settings, and Algorithm 1 summaries:
  `04_Evaluation/premise_test/results/lead_in/<period>_lead<days>.json`.
- Combined report: `04_Evaluation/premise_test/results/lead_in/sensitivity_30_90_180.json`.
- The 30-day-only report is named `sensitivity_30.json`.

Original baseline and weekly outputs keep their existing names. Interrupted
downloads remain in `.parquet.part` files and are resumed on the next download run.

Runs used four DuckDB threads and an 8 GB DuckDB memory limit. The largest June
run spilled about 26 GiB of temporary data to disk; DuckDB removed that temporary
directory when its connection closed. Saved experiment trades and scores remain
in `data/interim/`.
