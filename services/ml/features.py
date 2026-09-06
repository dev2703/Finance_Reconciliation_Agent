"""Label-free features. Floats are used only for ML, never money arithmetic."""

from decimal import Decimal, localcontext
from difflib import SequenceMatcher

from .contracts import Candidate

FEATURE_VERSION = "phase5-features-v1"
FEATURE_NAMES = (
    "absolute_delta",
    "relative_delta",
    "date_gap",
    "currency_match",
    "reference_similarity",
    "reference_missing",
    "party_agreement",
    "party_missing",
    "description_similarity",
    "description_missing",
    "source_count",
    "target_count",
    "graph_score",
    "graph_missing",
)


def _normalize(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _similarity(left: list[str | None], right: list[str | None]) -> tuple[float, float]:
    a = [_normalize(value) for value in left]
    b = [_normalize(value) for value in right]
    a, b = [value for value in a if value], [value for value in b if value]
    if not a or not b:
        return 0.0, 1.0
    return max(SequenceMatcher(None, x, y).ratio() for x in a for y in b), 0.0


def totals(candidate: Candidate) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 80
        return (
            sum((record.amount for record in candidate.sources), Decimal(0)),
            sum((record.amount for record in candidate.targets), Decimal(0)),
        )


def currency_valid(candidate: Candidate) -> bool:
    return len({record.currency for record in candidate.sources + candidate.targets}) == 1


def review_eligible(candidate: Candidate) -> bool:
    if not currency_valid(candidate):
        return False
    sources = {_normalize(record.party) for record in candidate.sources if record.party}
    targets = {_normalize(record.party) for record in candidate.targets if record.party}
    return not sources or not targets or sources == targets


def feature_vector(candidate: Candidate) -> list[float]:
    with localcontext() as context:
        context.prec = 80
        source, target = totals(candidate)
        delta = abs(source - target)
        relative = delta / max(abs(source), abs(target), Decimal("0.01"))
    references, references_missing = _similarity(
        [record.reference for record in candidate.sources],
        [record.reference for record in candidate.targets],
    )
    descriptions, descriptions_missing = _similarity(
        [record.description for record in candidate.sources],
        [record.description for record in candidate.targets],
    )
    sources = {_normalize(record.party) for record in candidate.sources if record.party}
    targets = {_normalize(record.party) for record in candidate.targets if record.party}
    days = max(
        abs((source_record.record_date - target_record.record_date).days)
        for source_record in candidate.sources
        for target_record in candidate.targets
    )
    return [
        float(min(delta, Decimal("1e15"))),
        float(relative),
        float(min(days, 3650)),
        float(currency_valid(candidate)),
        references,
        references_missing,
        float(bool(sources and targets) and sources == targets),
        float(not sources or not targets),
        descriptions,
        descriptions_missing,
        float(len(candidate.sources)),
        float(len(candidate.targets)),
        float(candidate.graph_score or 0),
        float(candidate.graph_score is None),
    ]
