# Phase 2–4 hardening

## PDF confidence and no-border tables

PDF ingestion first tries line-based table discovery, then retries with pdfplumber text-alignment
strategies when no ruled table exists. Text-derived tables retain normalized cell coordinates and
carry lower confidence than ruled tables.

Each page receives a native-text confidence. Pages below `OCR_FALLBACK_THRESHOLD` are rendered and
sent through OCR word-data extraction. OCR replaces native content only when its measured mean word
confidence is higher. The page records whether OCR was attempted, its confidence, and whether a
further structured extraction fallback is still required.

## Deterministic allocation API

`reconcile_records()` performs stable one-to-one matching, one-to-many allocation, then many-to-one
allocation before emitting unmatched records. All allocation arithmetic uses `Decimal`.

`POST /reconciliation/match` accepts bounded canonical source/target records and returns match
results plus generated audit events. It is stateless until Phase 10 reconciliation-run persistence
is implemented.

## Directed graph allocation

Graph candidate edges follow financial stage order:

```text
Invoice → Payment → Processor → Settlement → Bank transaction → Ledger entry
```

Conserved one-to-many and many-to-one groups are selected before ordinary paths. Declared fees may
bridge the exact difference between gross and net group totals. Every selected group returns
directed allocations, edge scores, reason codes, and confidence.
