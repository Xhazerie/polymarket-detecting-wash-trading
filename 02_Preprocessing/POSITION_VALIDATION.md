# Position validation

## Result

All 18 weekly windows passed a sampled comparison between the cleaned trade
ledger and an alternate representation of the raw fills:

- 100 wallet-market pairs sampled per window.
- 1,800 pair/window cases, representing 523 distinct wallet-market pairs.
- 13,613 block checkpoints compared.
- Zero mismatched block changes or cumulative positions.
- Maximum position difference: zero microshares.

The sample is selected deterministically by hashing wallet and market identifiers.
Repeated pairs across overlapping windows are expected. These counts do not imply
that every position in the full dataset has been checked.

## Why a direct user_position comparison is unavailable

The published `user_position` table is a state snapshot with fields for user,
token, amount, average price, realized PnL, and total bought. Its schema has no
historical timestamp. The snapshot's event cutoff is April 24, 2026 at 07:43:41 UTC;
state reads finished at 08:20:06 UTC. Our weekly endpoints are in 2024 and 2025.
Comparing these different dates would not yield a meaningful position accuracy
percentage. See the dataset [snapshot manifest](https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/blob/main/SNAPSHOT.json)
and upstream [UserPosition schema](https://github.com/enviodev/polymarket-indexer/blob/main/schema.graphql).

There is also a definition difference: the pipeline accumulates signed Yes-minus-No
trading exposure from zero at the lead-in boundary. The indexer tracks amounts per
token, caps sell reductions at the recorded holding, and updates positions for
additional lifecycle events. See its [position accounting](https://github.com/enviodev/polymarket-indexer/blob/main/src/utils/pnl.ts)
and [conditional-token handlers](https://github.com/enviodev/polymarket-indexer/blob/main/src/handlers/ConditionalTokens.ts).

## What the alternate comparison checks

1. The cleaned ledger assigns `dp_maker` to the maker and `-dp_maker` to the taker.
2. The reference ledger reads each raw fill as the maker's own order, derives its
   direction and outcome from raw asset IDs, and uses integer microshare amounts.
   It includes exchange-summary rows, which describe the taker's own order.
3. Both ledgers use the same window boundaries and condition-to-token metadata.
4. Changes are aggregated per wallet, market, and block, then accumulated from
   zero to compare positions at block boundaries.

Using the taker's own summary order provides a separate check of inferred taker
changes, including cases where the two sides trade different outcome tokens.
The upstream [exchange handler](https://github.com/enviodev/polymarket-indexer/blob/main/src/handlers/Exchange.ts)
also books order fills to the maker named in each raw event.

Block boundaries are used because maker legs and summary events have different
log indices inside a transaction. This check does not validate intermediate
positions or closure detection within a block.

## Reproduce

From the repository root:

```bash
uv run python 04_Evaluation/premise_test/04_validate_positions.py
```

Increase the sample if needed:

```bash
uv run python 04_Evaluation/premise_test/04_validate_positions.py --sample-size 500
```

Detailed samples and results are saved in
`04_Evaluation/premise_test/results/position_validation.json`.

## Remaining limits and next work

- This is a raw-fill consistency check, not independent ground truth: both sides
  rely on the same events and condition metadata.
- Holdings opened before the lead-in are unknown; both compared ledgers start at zero.
- Redemptions, token transfers, conversions, and other lifecycle changes are not
  included in this trading-exposure reconstruction.
- An actual balance comparison needs compatible historical state, or complete
  lifecycle reconstruction to a shared cutoff. The current `user_position`
  snapshot alone cannot supply that historical reference.
- Next, test longer lead-in periods and measure how positions and flags change.
