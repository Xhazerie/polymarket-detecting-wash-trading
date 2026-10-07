"""Shared settings for the premise test.

The premise test asks one question before we commit to this topic:
does our re-implementation of Algorithm 1 (Sirolly et al., 2025) flag clearly
more wash volume in a week the paper calls "peak" than in a week it calls "quiet"?
"""

from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
RAW = PROJECT / "data" / "raw"
INTERIM = PROJECT / "data" / "interim"
RESULTS = Path(__file__).resolve().parent / "results"

# The two exchange contracts. A fill row whose `taker` is one of these is the
# taker order's own summary row, which duplicates the maker rows in the same tx.
EXCHANGE_CONTRACTS = (
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",  # CTF Exchange
    "0xc5d563a36ae78145c45a50134d48a1215220f80a",  # NegRisk CTF Exchange
)

# Each window = a lead-in period (only used to learn positions and scores)
# followed by the target week (the week whose wash fraction we report).
# Lead-in exists because a closure needs the position history; a wallet that
# opened before the window would otherwise look like it never closed.
WINDOWS = {
    "dec2024": {  # paper: wash peaked at ~60% of weekly share volume in Dec 2024
        "months": ["2024-11", "2024-12"],
        "lead_start": "2024-11-01",
        "target_start": "2024-12-01",
        "target_end": "2024-12-08",
    },
    "jun2025": {  # paper: < 5% of weekly share volume from June 2025
        "months": ["2025-05", "2025-06"],
        "lead_start": "2025-05-01",
        "target_start": "2025-06-01",
        "target_end": "2025-06-08",
    },
}

# Algorithm 1 parameters, exactly as in the paper (§5.1 and §6)
C_CLOSURE = 0.005  # a closure = drawdown to <= 0.5% of the max position since the last closure
TOL = 1e-5  # relative L2 tolerance for the score iteration
THETA = 0.9  # fixed threshold used for the premise test

# Go / no-go rule from the feasibility check (feasible-polymarket-wash-trading.md)
GO_PEAK_MIN = 0.30
GO_QUIET_MAX = 0.10


from datetime import date, timedelta


def make_weekly_windows(start: date, end: date) -> dict:
    """Build consecutive target weeks within [start, end), each with 30 days of history.

    The returned settings have the same fields as WINDOWS, so extract() can
    process weekly datasets without changing its trade-cleaning logic.
    """
    windows = {}

    while start < end:
        # Stop at the analysis-period boundary; the final week may be shorter.
        target_end = min(start + timedelta(days=7), end)
        # Include history for position reconstruction, but do not count it as
        # target-week volume. This is 30 days, not a calendar month.
        lead_start = start - timedelta(days=30)

        # Raw fills are stored in monthly files. Include every month touched
        # by [lead_start, target_end); extract() filters rows to the exact dates.
        months = []
        month = lead_start.replace(day=1)
        while month < target_end:
            months.append(month.strftime("%Y-%m"))
            # Advance to the next calendar month, including December -> January.
            month = (
                date(month.year + 1, 1, 1)
                if month.month == 12
                else date(month.year, month.month + 1, 1)
            )

        # Use the target start date as the unique dataset name. ISO date strings
        # are used by extract() in UTC SQL filters; target_end is exclusive.
        windows[f"week_{start.isoformat()}"] = {
            "months": months,
            "lead_start": lead_start.isoformat(),
            "target_start": start.isoformat(),
            "target_end": target_end.isoformat(),
        }
        # Target weeks do not overlap; their 30-day historical lead-ins do.
        start = target_end

    return windows


# Keep the two baseline WINDOWS separate for existing Algorithm 1 and EDA runs.
# These periods generate nine windows each (18 total), anchored on Nov 1 / May 1
# rather than calendar Mondays. October / April files supply the early history.
WEEKLY_WINDOWS = {
    **make_weekly_windows(date(2024, 11, 1), date(2025, 1, 1)),
    **make_weekly_windows(date(2025, 5, 1), date(2025, 7, 1)),
}
