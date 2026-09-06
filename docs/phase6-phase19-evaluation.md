# Phase 6 evaluation harness

## One-command fixture benchmarks

```bash
python -m evaluation --suite all
```

Runs the offline ReconRiver, FinRCA, and FinBalance fixture packs under
`evaluation/datasets/fixtures/`, compares baseline vs system prediction JSONL files, and writes:

- `evaluation/reports/out/benchmark_result.json`
- `evaluation/reports/out/benchmark_report.md`

Override paths with `--fixtures` and `--output`. Restrict suites with repeated `--suite` flags.

## One-command custom demo pack (Phase 19)

```bash
python -m evaluation --demo-dir .data/demo --output .data/evaluation
```

Seeds the deterministic 40-case pack, scores baseline vs candidate predictions, and writes
`benchmark.json` plus `benchmark.md`. Override the pack seed with `--seed`.

## Metric coverage

The shared metric engine reports precision, recall, F1, root-cause accuracy, evidence
precision/recall, resolution accuracy, hard-negative false-positive rate, automation rate,
false-positive/false-negative financial exposure, latency, LLM tokens, and estimated cost.

Money fields stay on `Decimal`. Fixture and demo candidate predictions are acceptance fixtures,
not a claim about live end-to-end system accuracy. Replace prediction JSONL files with real
workflow exports to measure the current system.
