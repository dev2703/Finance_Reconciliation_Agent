# Phase 6 and Phase 19 — Demo evaluation

Generate the deterministic 40-case demo pack and compare the included simple baseline with the
expected candidate output in one command:

```bash
python -m evaluation --demo-dir .data/demo --output-dir .data/evaluation
```

The command writes `cases.jsonl`, baseline and candidate prediction JSONL files, a seed manifest,
`benchmark.json`, and `benchmark.md`. The seed defaults to `20260906` and can be overridden with
`--seed`.

The pack contains exact matches, timing and fee differences, partial payments, split settlements,
duplicates, wrong allocations, missing bank/ledger records, hard negatives, multi-hop cases, and
messy PDF/table cases. Every case carries an expected outcome, evidence ID, exact string money, and
stable entity grouping.

The included candidate predictions are ground-truth acceptance fixtures, not a claim about current
end-to-end system accuracy. Replace either prediction JSONL file with real system output to measure
precision, recall, F1, root-cause/evidence/resolution quality, automation, financial exposure,
latency, tokens, and cost through the same harness.
