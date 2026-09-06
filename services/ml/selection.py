"""Review selection over a complete competing candidate batch."""

import math
from collections import defaultdict

from .features import review_eligible

REVIEW_POLICY = {"version": "record-competition-v1", "minimum_margin": 0.05}


def review_mask(candidates, scores, threshold):
    scores = [float(score) for score in scores]
    if len(candidates) != len(scores) or len({candidate.id for candidate in candidates}) != len(
        candidates
    ):
        raise ValueError("Candidate IDs must be unique and scores must align")
    if any(not math.isfinite(score) or not 0 <= score <= 1 for score in scores):
        raise ValueError("Scores must be finite probabilities")
    if threshold is not None and (not math.isfinite(threshold) or not 0 <= threshold <= 1):
        raise ValueError("Threshold must be a finite probability")

    eligible = [review_eligible(candidate) for candidate in candidates]
    resources = [
        {record.id for record in candidate.sources + candidate.targets} for candidate in candidates
    ]
    users = defaultdict(list)
    for index, record_ids in enumerate(resources):
        if eligible[index]:
            for record_id in record_ids:
                users[record_id].append(index)
    selected = []
    for index, record_ids in enumerate(resources):
        rivals = {rival for record_id in record_ids for rival in users[record_id] if rival != index}
        selected.append(
            bool(
                eligible[index]
                and threshold is not None
                and scores[index] >= threshold
                and all(
                    scores[index] - scores[rival] >= REVIEW_POLICY["minimum_margin"]
                    for rival in rivals
                )
            )
        )
    return selected
