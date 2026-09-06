# Phase 5 runtime integration

Phase 5 trains a locally trusted candidate-ranking artifact for the synthetic
demo only. It never approves, posts, or changes accounting records, and is not
enabled in the normal runtime workflow without labeled match data.

## Train a local artifact

For the self-contained synthetic demo, run:

```bash
python -m evaluation.train_ml --demo
ML_MODEL_DIRECTORY=.data/phase5-demo/artifact uv run uvicorn apps.api.main:app --reload
```

The first command produces the ignored `.data/phase5-demo/` artifact, input,
and metrics report. The second command makes its review-only endpoint available.
For a custom fixture location, use:

```bash
python -m evaluation.train_ml \
  --dataset evaluation/train_ml/data/synthetic_pairs.jsonl \
  --write-synthetic \
  --artifact-dir artifacts/phase5-ml \
  --report artifacts/phase5-ml/metrics.json
```

The pipeline splits disconnected worlds before fitting, calibrates on held-out
validation worlds, evaluates frozen thresholds on test worlds, and writes a
checksum alongside the model. `model.joblib` must be operator-controlled: it is
not safe to load artifacts from untrusted storage.

## Serve review-only suggestions

For the synthetic demo only, set `ML_MODEL_DIRECTORY` to the artifact directory before starting the API, or
pass `ml_model_directory` to `create_app()` in an embedded deployment. Then use
`POST /demo/ml-review` with a complete batch of candidates. The
endpoint returns `REVIEW` or `UNRESOLVED` only, rejects unavailable/incompatible
artifacts with HTTP 503, and explicitly sets `automatic_action_eligible: false`.

The bundled synthetic data establishes a reproducible implementation gate; it
does not establish calibration on representative external financial data. That
remaining acceptance gate requires approved ReconRiver/FinRCA/custom production
holdouts and must be completed before enabling any broader workflow.
