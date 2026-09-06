INSERT INTO documents (id, filename, media_type, sha256, uploaded_at, source)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    'sample-invoice.json',
    'application/json',
    'phase0-fixture',
    '2026-01-15T00:00:00Z',
    'fixture'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO financial_records (
    id, record_type, external_id, amount, currency, record_date, source_document_id, payload
)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'invoice',
    'INV-1001',
    1200.00,
    'USD',
    '2026-01-15',
    '00000000-0000-0000-0000-000000000010',
    '{"invoice_number":"INV-1001","vendor_id":"vendor-42","tax_amount":"100.00"}'
)
ON CONFLICT (id) DO NOTHING;
