# Dataset adapter contract

`load_reconriver()`, `load_finrca()`, and `load_custom_benchmark()` return frozen
`DatasetCase` values. Each value retains the original ground truth, model-visible
records, exact `Decimal` money, source-file/row provenance, and three leakage-control
keys: scenario, related entity IDs, and generator seed.

The custom benchmark is UTF-8 JSONL with exactly these fields per row:

```json
{"case_id":"custom-1","scenario_id":"fee","generator_seed":42,"group_entity_ids":["vendor-1","payment-1"],"label":"KNOWN_FEE","ground_truth":{"expected_amount":"1.25"},"records":[{"id":"payment-1","amount":"101.25"}]}
```

Money must be encoded as decimal strings or integers, never JSON floats. Empty or
duplicate identifiers, missing evidence, conflicting/duplicate cases, malformed
numbers, non-finite values, unexpected columns/fields, and ReconRiver checksum or
scenario mismatches fail with `DatasetFormatError`. Adapters perform local file I/O
only; downloading or generating the source datasets is outside this contract.

### Pair training conversion

`training_examples_from_cases()` accepts **custom** cases whose `ground_truth`
includes:

- `is_match` (bool)
- `source_ids` / `target_ids` (non-empty unique string lists)
- optional `is_hard_negative` (bool)
- optional `graph_score` (decimal string in `[0, 1]`)

Each referenced record must include `id`, `record_type`, `amount`, `currency`, and
ISO `record_date`, plus optional `reference`, `party`, and `description`.
