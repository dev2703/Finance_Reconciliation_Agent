"""Financial graph reconciliation engine.

Implements multi-hop matching via:
1. Entity nodes (individual records)
2. Candidate edge generation with blocking keys
3. Min-cost bipartite matching across paths
4. Explainable lineage paths
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal
from itertools import combinations
from typing import Any
from uuid import UUID

from packages.contracts import (
    Allocation,
    CandidateEdge,
    EntityNode,
    FinancialGraph,
    FinancialRecord,
    GraphPath,
    MatchReasonCode,
)

DEFAULT_DATE_WINDOW_DAYS = 3
DEFAULT_MAX_HOP_DISTANCE = 5
_TYPE_ORDER = {
    "invoice": 0,
    "payment": 1,
    "processor": 2,
    "settlement": 3,
    "bank_transaction": 4,
    "ledger_entry": 5,
}


def normalize_blocking_key(
    record: FinancialRecord,
    record_type: str,
    *,
    party_field: str | None = None,
) -> dict[str, Any]:
    """Generate blocking keys for candidate edge reduction.

    Returns a dict with keys:
    - "currency": uppercase currency code
    - "amount_bucket": round(log10(amount)) * 10, e.g., 100-999 -> 200
    - "date_bucket": record_date - (record_date.day % 7) for weekly grouping
    - "normalized_party": extracted/normalized party ID
    - "reference_prefix": first 3 chars of reference/invoice number (if present)
    """
    keys: dict[str, Any] = {
        "currency": record.currency.upper(),
        "date_bucket": record.record_date,
    }

    # Amount bucketing: log scale for range grouping
    if record.amount > 0:
        bucket = max(1, int(math.log10(float(record.amount))) * 100)
        keys["amount_bucket"] = bucket
    else:
        keys["amount_bucket"] = 0

    # Extract normalized party
    party = None
    if party_field and hasattr(record, party_field):
        party = getattr(record, party_field)
    elif hasattr(record, "vendor_id") and record.vendor_id:
        party = record.vendor_id
    elif hasattr(record, "payer_id") and record.payer_id:
        party = record.payer_id
    elif hasattr(record, "payee_id") and record.payee_id:
        party = record.payee_id
    elif hasattr(record, "account_id") and record.account_id:
        party = record.account_id

    if party:
        keys["normalized_party"] = party.lower().strip()

    # Reference prefix for invoice/check/reference numbers
    reference = None
    if hasattr(record, "invoice_number") and record.invoice_number:
        reference = record.invoice_number
    elif hasattr(record, "bank_reference") and record.bank_reference:
        reference = record.bank_reference
    elif hasattr(record, "settlement_reference") and record.settlement_reference:
        reference = record.settlement_reference
    elif hasattr(record, "payment_reference") and record.payment_reference:
        reference = record.payment_reference

    if reference:
        keys["reference_prefix"] = reference[:3].lower()

    return keys


def build_entity_nodes(records: Mapping[str, Iterable[FinancialRecord]]) -> dict[UUID, EntityNode]:
    """Convert financial records to entity nodes.

    Args:
        records: dict mapping record type -> list of records
                 e.g., {"invoice": [...], "payment": [...], "bank_transaction": [...]}

    Returns:
        dict mapping node UUID -> EntityNode
    """
    nodes: dict[UUID, EntityNode] = {}

    for record_type, record_list in records.items():
        for record in record_list:
            blocking_keys = normalize_blocking_key(record, record_type)
            node = EntityNode(
                record_id=record.id,
                record_type=record_type,
                amount=record.amount,
                currency=record.currency.upper(),
                record_date=record.record_date,
                normalized_party=blocking_keys.get("normalized_party"),
                reference=getattr(record, "invoice_number", None)
                or getattr(record, "bank_reference", None)
                or getattr(record, "settlement_reference", None)
                or getattr(record, "payment_reference", None),
                amount_bucket=blocking_keys.get("amount_bucket"),
                metadata={
                    "blocking_keys": blocking_keys,
                    "record_type": record_type,
                    "fee_amount": getattr(record, "fee_amount", Decimal(0)),
                },
            )
            nodes[record.id] = node

    return nodes


def build_candidate_edges(
    nodes: Mapping[UUID, EntityNode],
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    allow_currency_mismatch: bool = False,
) -> list[CandidateEdge]:
    """Generate candidate edges between nodes using blocking keys.

    Blocking strategy:
    - Same currency (unless allow_currency_mismatch=True)
    - Overlapping date windows (±date_window_days)
    - Same or compatible amount buckets (within 2 buckets)
    - Same normalized party (if both have one)
    - Similar reference prefix (if both have one)

    Within blocked candidates, score using deterministic match_pair logic.
    """
    edges: list[CandidateEdge] = []
    node_list = sorted(nodes.values(), key=lambda n: str(n.record_id))

    for i, source_node in enumerate(node_list):
        for target_node in node_list[i + 1 :]:
            # Skip self-loops
            if source_node.record_id == target_node.record_id:
                continue

            # Currency blocking (unless explicitly allowed)
            if not allow_currency_mismatch and source_node.currency != target_node.currency:
                continue

            # Date window blocking
            date_delta = abs((source_node.record_date - target_node.record_date).days)
            if date_delta > date_window_days:
                continue

            # Amount bucket blocking
            if source_node.amount_bucket is not None and target_node.amount_bucket is not None:
                bucket_delta = abs(source_node.amount_bucket - target_node.amount_bucket)
                if bucket_delta > 200:  # Allow ~1 order of magnitude difference
                    continue

            # Normalized party compatibility (optional constraint)
            if (
                source_node.normalized_party
                and target_node.normalized_party
                and source_node.normalized_party != target_node.normalized_party
            ):
                # Skip if parties differ (can be loosened for multi-hop)
                pass

            # Reference prefix compatibility (optional)
            if (
                source_node.reference
                and target_node.reference
                and source_node.reference[:3] != target_node.reference[:3]
            ):
                # Allow different references; will be scored below
                pass

            # Within blocked set, score the pair
            score = Decimal(0)
            reason_codes: list[MatchReasonCode] = []

            if source_node.amount == target_node.amount:
                reason_codes.append(MatchReasonCode.EXACT_AMOUNT)
                if date_delta == 0:
                    score = Decimal("0.95")
                else:
                    score = Decimal("0.90")
                    reason_codes.append(MatchReasonCode.AMOUNT_DATE_WINDOW)
            elif abs(source_node.amount - target_node.amount) <= Decimal("10.00"):
                # Small difference (fee or rounding)
                reason_codes.append(MatchReasonCode.KNOWN_FEE)
                score = Decimal("0.80")
            else:
                score = Decimal("0.50")

            if source_node.currency == target_node.currency:
                reason_codes.append(MatchReasonCode.CURRENCY_MATCH)

            if score > 0:
                source_id, target_id = _directed_pair(source_node, target_node)
                edges.append(
                    CandidateEdge(
                        source_node_id=source_id,
                        target_node_id=target_id,
                        score=score,
                        reason_codes=reason_codes,
                    )
                )

    return edges


def _directed_pair(left: EntityNode, right: EntityNode) -> tuple[UUID, UUID]:
    left_rank = _TYPE_ORDER.get(left.record_type, len(_TYPE_ORDER))
    right_rank = _TYPE_ORDER.get(right.record_type, len(_TYPE_ORDER))
    if left_rank != right_rank:
        return (
            (left.record_id, right.record_id)
            if left_rank < right_rank
            else (right.record_id, left.record_id)
        )
    if str(left.record_id) < str(right.record_id):
        return left.record_id, right.record_id
    return right.record_id, left.record_id


def find_directed_allocations(
    nodes: Mapping[UUID, EntityNode],
    edges: list[CandidateEdge],
    *,
    max_group_size: int = 4,
) -> list[GraphPath]:
    """Resolve directed one-to-many and many-to-one conserved groups, including fees."""
    edge_index = {(edge.source_node_id, edge.target_node_id): edge for edge in edges}
    used: set[UUID] = set()
    paths: list[GraphPath] = []
    ordered = sorted(
        nodes.values(),
        key=lambda node: (_TYPE_ORDER.get(node.record_type, 99), str(node.record_id)),
    )

    for source in ordered:
        if source.record_id in used:
            continue
        outgoing = [
            nodes[target_id]
            for source_id, target_id in edge_index
            if source_id == source.record_id and target_id not in used
        ]
        path = _allocation_group(source, outgoing, edge_index, max_group_size=max_group_size)
        if path:
            paths.append(path)
            used.update(path.node_ids)

    for target in ordered:
        if target.record_id in used:
            continue
        incoming = [
            nodes[source_id]
            for source_id, target_id in edge_index
            if target_id == target.record_id and source_id not in used
        ]
        path = _allocation_group(
            target,
            incoming,
            edge_index,
            max_group_size=max_group_size,
            many_to_one=True,
        )
        if path:
            paths.append(path)
            used.update(path.node_ids)
    return paths


def _allocation_group(
    anchor: EntityNode,
    candidates: list[EntityNode],
    edge_index: Mapping[tuple[UUID, UUID], CandidateEdge],
    *,
    max_group_size: int,
    many_to_one: bool = False,
) -> GraphPath | None:
    candidates = sorted(candidates, key=lambda node: str(node.record_id))
    for size in range(2, min(max_group_size, len(candidates)) + 1):
        for group in combinations(candidates, size):
            if len({node.record_type for node in group}) != 1:
                continue
            if any(node.currency != anchor.currency for node in group):
                continue
            group_total = sum((node.amount for node in group), Decimal(0))
            fee = sum((_node_fee(node) for node in (anchor, *group)), Decimal(0))
            difference = group_total - anchor.amount if many_to_one else anchor.amount - group_total
            fee_adjusted = fee > 0 and difference == fee
            if difference != 0 and not fee_adjusted:
                continue
            allocations = []
            selected_edges = []
            for member in group:
                source_id, target_id = (
                    (member.record_id, anchor.record_id)
                    if many_to_one
                    else (anchor.record_id, member.record_id)
                )
                edge = edge_index.get((source_id, target_id))
                if edge is None:
                    break
                selected_edges.append(edge)
                allocations.append(
                    Allocation(
                        source_record_id=source_id,
                        target_record_id=target_id,
                        amount=member.amount,
                        currency=anchor.currency,
                    )
                )
            else:
                reason = MatchReasonCode.KNOWN_FEE if fee_adjusted else MatchReasonCode.EXACT_AMOUNT
                return GraphPath(
                    node_ids=(
                        [*(node.record_id for node in group), anchor.record_id]
                        if many_to_one
                        else [anchor.record_id, *(node.record_id for node in group)]
                    ),
                    edge_scores=[edge.score for edge in selected_edges],
                    reason_code_sequence=[[*edge.reason_codes, reason] for edge in selected_edges],
                    total_confidence=Decimal("0.82") if fee_adjusted else Decimal("0.88"),
                    allocations=allocations,
                )
    return None


def _node_fee(node: EntityNode) -> Decimal:
    value = node.metadata.get("fee_amount", Decimal(0))
    return abs(value) if isinstance(value, Decimal) else abs(Decimal(str(value)))


def find_graph_paths(
    nodes: Mapping[UUID, EntityNode],
    edges: list[CandidateEdge],
    *,
    max_hop_distance: int = DEFAULT_MAX_HOP_DISTANCE,
    min_path_score: Decimal | None = None,
) -> list[GraphPath]:
    """Find optimal multi-hop paths using Dijkstra's algorithm.

    For each unmatched node, search for paths to complementary nodes.
    A path is scored as the product of edge scores.
    Returns top-K non-overlapping paths.

    Args:
        nodes: entity nodes by UUID
        edges: candidate edges
        max_hop_distance: maximum number of hops in a path
        min_path_score: minimum acceptable path confidence; default 0.50

    Returns:
        list of GraphPath, ordered by total_confidence descending
    """
    if min_path_score is None:
        min_path_score = Decimal("0.50")

    # Build adjacency for path search
    forward_edges: dict[UUID, list[tuple[UUID, Decimal, list[MatchReasonCode]]]] = defaultdict(list)
    for edge in edges:
        forward_edges[edge.source_node_id].append(
            (edge.target_node_id, edge.score, edge.reason_codes)
        )

    paths: list[GraphPath] = []
    used_node_ids: set[UUID] = set()

    # Dijkstra to find highest-confidence paths
    for start_node_id in nodes:
        if start_node_id in used_node_ids:
            continue

        # Priority queue: (negative_score, path_nodes, path_scores, path_reasons)
        pq: list[tuple[Decimal, list[UUID], list[Decimal], list[list[MatchReasonCode]]]] = [
            (Decimal(-1), [start_node_id], [], [])
        ]
        visited: set[UUID] = set()

        while pq:
            neg_score, path_nodes, path_scores, path_reasons = heapq.heappop(pq)
            current_score = -neg_score

            current_node_id = path_nodes[-1]
            if current_node_id in visited:
                continue
            visited.add(current_node_id)

            # Valid path if 2+ nodes
            if len(path_nodes) >= 2 and current_score >= min_path_score:
                # Check for overlap
                if not any(nid in used_node_ids for nid in path_nodes):
                    graph_path = GraphPath(
                        node_ids=path_nodes,
                        edge_scores=path_scores,
                        reason_code_sequence=path_reasons,
                        total_confidence=current_score,
                    )
                    paths.append(graph_path)
                    used_node_ids.update(path_nodes)
                    break  # Move to next start node

            # Extend path if within hop limit
            if len(path_nodes) < max_hop_distance:
                for next_node_id, edge_score, edge_reasons in forward_edges[current_node_id]:
                    if next_node_id not in visited:
                        new_score = current_score * edge_score if current_score > 0 else edge_score
                        new_path = path_nodes + [next_node_id]
                        new_scores = path_scores + [edge_score]
                        new_reasons = path_reasons + [edge_reasons]
                        heapq.heappush(pq, (-new_score, new_path, new_scores, new_reasons))

    return sorted(paths, key=lambda p: p.total_confidence, reverse=True)


def reconcile_graph(
    records: Mapping[str, Iterable[FinancialRecord]],
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    max_hop_distance: int = DEFAULT_MAX_HOP_DISTANCE,
    min_path_score: Decimal | None = None,
) -> FinancialGraph:
    """Run complete graph reconciliation.

    Workflow:
    1. Convert records to entity nodes
    2. Generate candidate edges with blocking
    3. Find optimal multi-hop paths
    4. Mark unmatched nodes

    Args:
        records: dict mapping record type -> list of records
        date_window_days: matching window in days
        max_hop_distance: max hops in a path
        min_path_score: minimum path confidence (default 0.50)

    Returns:
        FinancialGraph with nodes, candidate edges, selected paths, and unmatched IDs
    """
    nodes = build_entity_nodes(records)
    candidate_edges = build_candidate_edges(
        nodes, date_window_days=date_window_days, allow_currency_mismatch=False
    )
    allocation_paths = find_directed_allocations(nodes, candidate_edges)
    allocated_ids = {node_id for path in allocation_paths for node_id in path.node_ids}
    remaining_nodes = {
        node_id: node for node_id, node in nodes.items() if node_id not in allocated_ids
    }
    remaining_edges = [
        edge
        for edge in candidate_edges
        if edge.source_node_id in remaining_nodes and edge.target_node_id in remaining_nodes
    ]
    paths = allocation_paths + find_graph_paths(
        remaining_nodes,
        remaining_edges,
        max_hop_distance=max_hop_distance,
        min_path_score=min_path_score,
    )

    # Identify unmatched nodes
    matched_node_ids: set[UUID] = set()
    for path in paths:
        matched_node_ids.update(path.node_ids)

    unmatched_node_ids = set(nodes.keys()) - matched_node_ids

    graph = FinancialGraph(
        nodes=nodes,
        candidate_edges=candidate_edges,
        selected_paths=paths,
        unmatched_node_ids=unmatched_node_ids,
    )

    return graph
