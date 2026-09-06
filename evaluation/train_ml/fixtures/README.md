# Custom pair JSONL for Phase 5 train_ml
#
# Each row follows services/ml/datasets custom contract. Training semantics live
# in ground_truth: is_match, is_hard_negative, source_ids, target_ids, graph_score.
# Generate a full synthetic set with:
#   python -m evaluation.train_ml --write-synthetic PATH --output ARTIFACT_DIR
