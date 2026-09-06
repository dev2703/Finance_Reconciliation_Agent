# Demo upload pack

These fictional files are designed for a short product demo. Upload them from
the **Documents** screen in this order:

| File | Select this record type | Expected result |
|---|---|---|
| `01-invoices-september.csv` | `Invoice` | Four normalized invoices with vendor, due-date, tax, and provenance fields. |
| `02-payments-september.csv` | `Payment` | Four normalized customer payments whose references link to the invoices. |
| `03-bank-exceptions-september.csv` | `Bank transaction` | Six normalized bank movements: two exact deposits, a fee-adjusted settlement, a timing difference, a bank fee, and an unknown remittance. |

After each upload, wait for **Parsed**, inspect the normalized preview, and
click **Confirm import**. The files are deliberately fictional and contain no
customer or bank data.

The current free Render deployment has no persistent ingestion worker, so real
uploads remain queued there. For a video, use the already-deployed
`/reconciliation` → **Seed demo & reconcile** flow for reconciliation results,
or run `python -m services.ingestion.worker` locally while demonstrating the
upload/preview/confirmation flow.
