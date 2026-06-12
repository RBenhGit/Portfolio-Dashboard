# Verification Data

Broker-issued statements used for **manual cross-checking** of dashboard numbers
(positions, market values, quarterly returns) against IBI's own reports.
They are *not* loaded by any automated test.

| File | What it is |
|------|-----------|
| `פורטפוליו 2026-04-02.xlsx` | IBI portfolio statement snapshot (2026-04-02) — compare holdings & valuations |
| `תשואה Q1 2026.xlsx` | IBI Q1 2026 return report — compare period returns |

The `.xlsx` files contain personal account data and are gitignored
(`tests/verification_data/*.xlsx`); only this README is tracked.
