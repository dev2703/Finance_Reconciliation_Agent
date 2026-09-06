# Phase 5 synthetic-demo validation

Status: **validated for the bundled synthetic demo only**. This is not a
production-calibration claim.

Run the demo from a clean checkout:

```bash
uv run python -m evaluation.train_ml --demo
```

It creates ignored local outputs under `.data/phase5-demo/`: the deterministic
pair fixture, a checksum-verified model artifact, and `metrics.json`.

## Acceptance gate

- grouped train/validation/test worlds have no record or entity overlap;
- calibration is fitted only on validation worlds;
- frozen review thresholds pass the held-out test-world constraints;
- test hard-negative false-positive rate is zero;
- the artifact validates its feature contract and checksum;
- API inference is configured explicitly and returns review-only suggestions.

## Latest local run — 2026-09-06

`python -m evaluation.train_ml --demo` selected logistic regression. The held-out
test partition contained 11 candidates and 4 hard negatives. It passed the
review gate with zero review false positives and zero hard-negative false
positives. The generated artifact supports only `payment -> settlement`
relationships and every output has `automatic_action_eligible: false`.

The generated data is deliberately separable, so its perfect classification
metrics are a regression signal, not a real-world performance estimate.
