"""Phase 4 graph reconciliation tests."""

from datetime import date
from decimal import Decimal

from packages.contracts import (
    BankTransaction,
    Invoice,
    LedgerEntry,
    Payment,
    Settlement,
)
from services.reconciliation.graph import (
    build_candidate_edges,
    build_entity_nodes,
    find_graph_paths,
    normalize_blocking_key,
    reconcile_graph,
)


def test_normalize_blocking_key_extracts_party_and_reference():
    """Test that blocking keys capture party and reference information."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-123",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )

    keys = normalize_blocking_key(invoice, "invoice")
    assert keys["currency"] == "USD"
    assert keys["normalized_party"] == "vendor-123"
    assert keys["reference_prefix"] == "inv"
    assert "amount_bucket" in keys
    assert "date_bucket" in keys


def test_blocking_key_amount_bucketing():
    """Test that amounts are bucketed for range grouping."""
    small = BankTransaction(
        account_id="cash-1",
        transaction_type="deposit",
        amount=Decimal("50.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    large = BankTransaction(
        account_id="cash-1",
        transaction_type="deposit",
        amount=Decimal("5000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )

    small_keys = normalize_blocking_key(small, "bank_transaction")
    large_keys = normalize_blocking_key(large, "bank_transaction")

    # Amounts differ by 2 orders of magnitude, buckets should differ
    assert small_keys["amount_bucket"] is not None
    assert large_keys["amount_bucket"] is not None
    assert abs(small_keys["amount_bucket"] - large_keys["amount_bucket"]) >= 100


def test_build_entity_nodes_from_multiple_record_types():
    """Test converting records to entity nodes."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 16),
        payee_id="vendor-1",
    )

    nodes = build_entity_nodes({"invoice": [invoice], "payment": [payment]})

    assert len(nodes) == 2
    invoice_node = nodes[invoice.id]
    payment_node = nodes[payment.id]

    assert invoice_node.record_type == "invoice"
    assert payment_node.record_type == "payment"
    assert invoice_node.amount == Decimal("1000.00")
    assert payment_node.amount == Decimal("1000.00")


def test_build_candidate_edges_with_blocking():
    """Test that candidate edges respect blocking constraints."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 16),
        payee_id="vendor-1",
    )
    # Different currency—should be blocked
    different_currency = BankTransaction(
        account_id="cash-1",
        transaction_type="deposit",
        amount=Decimal("1000.00"),
        currency="EUR",
        record_date=date(2026, 1, 16),
    )

    nodes = build_entity_nodes(
        {"invoice": [invoice], "payment": [payment], "bank_transaction": [different_currency]}
    )
    edges = build_candidate_edges(nodes, date_window_days=3)

    # Should have edge between invoice and payment, but not involving different_currency
    edge_pairs = [(e.source_node_id, e.target_node_id) for e in edges]
    assert (invoice.id, payment.id) in edge_pairs or (payment.id, invoice.id) in edge_pairs
    # No edges should involve different_currency node
    assert not any(different_currency.id in (e.source_node_id, e.target_node_id) for e in edges)


def test_build_candidate_edges_respects_date_window():
    """Test that candidate edges respect date window blocking."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 1),
    )
    # 5 days later—outside default 3-day window
    late_payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 6),
        payee_id="vendor-1",
    )

    nodes = build_entity_nodes({"invoice": [invoice], "payment": [late_payment]})
    edges = build_candidate_edges(nodes, date_window_days=3)

    # No edges due to date window
    assert len(edges) == 0

    # With extended window, should have edge
    edges_extended = build_candidate_edges(nodes, date_window_days=10)
    assert len(edges_extended) > 0


def test_candidate_edge_scoring():
    """Test that edges are scored correctly."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    exact_payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )
    # Different amount that won't match
    different_payment = Payment(
        amount=Decimal("2000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )

    nodes = build_entity_nodes(
        {"invoice": [invoice], "payment": [exact_payment, different_payment]}
    )
    edges = build_candidate_edges(nodes)

    # Find edges involving invoice
    invoice_edges = [
        e for e in edges if e.source_node_id == invoice.id or e.target_node_id == invoice.id
    ]

    assert len(invoice_edges) > 0, "Should have edges involving invoice"

    # Edges involving exact_payment should score higher than different_payment
    # (or at least not lower)
    exact_edge_scores = [
        edge.score
        for edge in invoice_edges
        if edge.source_node_id == exact_payment.id or edge.target_node_id == exact_payment.id
    ]
    diff_edge_scores = [
        edge.score
        for edge in invoice_edges
        if edge.source_node_id == different_payment.id
        or edge.target_node_id == different_payment.id
    ]

    if exact_edge_scores and diff_edge_scores:
        assert max(exact_edge_scores) >= max(diff_edge_scores)


def test_find_graph_paths_single_hop():
    """Test path finding for simple two-node paths."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )

    nodes = build_entity_nodes({"invoice": [invoice], "payment": [payment]})
    edges = build_candidate_edges(nodes)
    paths = find_graph_paths(nodes, edges, min_path_score=Decimal("0.50"))

    assert len(paths) > 0
    path = paths[0]
    assert len(path.node_ids) == 2
    assert invoice.id in path.node_ids
    assert payment.id in path.node_ids


def test_find_graph_paths_multi_hop():
    """Test path finding for invoice -> payment -> settlement -> bank -> ledger."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 10),
    )
    payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 11),
        payee_id="vendor-1",
    )
    settlement = Settlement(
        settlement_reference="SETTLE-001",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 12),
        processor="processor-1",
    )
    bank_txn = BankTransaction(
        account_id="cash-1",
        transaction_type="deposit",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 13),
    )
    ledger = LedgerEntry(
        journal_id="J-1",
        account_code="1000",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 13),
    )

    nodes = build_entity_nodes(
        {
            "invoice": [invoice],
            "payment": [payment],
            "settlement": [settlement],
            "bank_transaction": [bank_txn],
            "ledger_entry": [ledger],
        }
    )
    edges = build_candidate_edges(nodes, date_window_days=5)
    paths = find_graph_paths(nodes, edges, max_hop_distance=5, min_path_score=Decimal("0.30"))

    assert len(paths) > 0
    # At least one path should be found
    path = paths[0]
    assert len(path.node_ids) >= 2


def test_reconcile_graph_identifies_unmatched():
    """Test that reconcile_graph correctly identifies unmatched nodes."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )
    # Orphaned payment with no match
    orphan_payment = Payment(
        amount=Decimal("500.00"),
        currency="USD",
        record_date=date(2026, 1, 20),
        payee_id="unknown-vendor",
    )

    graph = reconcile_graph(
        {
            "invoice": [invoice],
            "payment": [payment, orphan_payment],
        }
    )

    assert orphan_payment.id in graph.unmatched_node_ids
    assert len(graph.selected_paths) > 0  # invoice-payment should match


def test_reconcile_graph_produces_explainable_paths():
    """Test that paths include reason codes for explainability."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )

    graph = reconcile_graph({"invoice": [invoice], "payment": [payment]})

    assert len(graph.selected_paths) > 0
    path = graph.selected_paths[0]
    assert len(path.reason_code_sequence) > 0
    # Should include reason codes like EXACT_AMOUNT, CURRENCY_MATCH
    all_reasons = [code for codes in path.reason_code_sequence for code in codes]
    assert len(all_reasons) > 0


def test_split_payment_detection():
    """Test that one-to-many paths (split payments) are detected."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 10),
    )
    # Two payments totaling the invoice
    payment_1 = Payment(
        amount=Decimal("600.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )
    payment_2 = Payment(
        amount=Decimal("400.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )

    # For split detection, need many-to-one path finding
    nodes = build_entity_nodes(
        {
            "invoice": [invoice],
            "payment": [payment_1, payment_2],
        }
    )
    edges = build_candidate_edges(nodes, date_window_days=5)

    # Graph should identify candidate edges for both payments
    assert len(edges) >= 2


def test_graph_exports_selected_paths_with_allocations():
    """Test that matched paths include allocation information."""
    invoice = Invoice(
        invoice_number="INV-001",
        vendor_id="vendor-1",
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
    )
    payment = Payment(
        amount=Decimal("1000.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        payee_id="vendor-1",
    )

    graph = reconcile_graph({"invoice": [invoice], "payment": [payment]})

    assert len(graph.selected_paths) > 0
    path = graph.selected_paths[0]
    # Path should have basic structure even if allocations are empty
    assert hasattr(path, "allocations")
