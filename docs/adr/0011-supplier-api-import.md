---
status: accepted
date: 2026-11-02
---

# Supplier API imports: snapshot when offered, overlap and reconcile when not

**The problem.** A supplier API that pages a live list by offset, newest first, shifts under the reader: new
and updated products jump to the front. A naive scan of a mock with 2 inserts and 3 updates per request read
185 products twice and missed 185 of 5,104.

**Chosen** (`supplier_import.py`).

- **v2 (snapshot token)** when the supplier offers it: every page reads one frozen copy, keyset by SKU.
- **v1 (offset)** otherwise:
  1. Pages overlap by one item. If a page doesn't start with the previous page's last SKU, the boundary moved;
     the importer finds where the previous page's SKUs went (looking up to 5 pages ahead) and continues after
     them. Unchanged products can only shift *later* (everything moves toward the end), so this alone makes the
     scan exact for them.
  2. Changed products moved to the front, so they're newer than the scan's first page. A reconciliation pass
     re-reads from the top everything newer than that, and repeats from the top until one page holds every
     change made during the previous pass. "Newer" uses the supplier's own `updated_at` (the watermark is the
     newest timestamp on a pass's first page), so the two clocks never need to agree.
  3. Versions are deduplicated by (sku, updated_at); an older version never overwrites a newer one.
- **Resumable**: progress is saved in `import_state` after every page, in the same transaction as that page's
  products. A failed import resumes from the saved offset and anchor SKUs.
- **Rate limits and errors**: 429s are waited out honouring `Retry-After` (up to 20); 5xx and connection errors
  are retried with backoff, 3 in a row stops the import (state saved, error recorded).
- Products go through the same validation and upsert as feed files (`feeds.upsert_rows`), and the products that
  need it are queued for enrichment.

Measured: 5,206 products under drift and 3% 429s, 0 missing, 0 extra, 0 outdated; the same after a failure at
request 20 and a resume.

## Alternatives

- **Dedupe by (sku, updated_at) only**, as the plan's first line suggests: removes duplicates, but can't recover
  the products that moved behind the scan.
- **Re-scan until two scans agree**: never converges while the supplier keeps changing, and costs full scans.
- **Our clock as the watermark**: needs a skew margin, and any margin larger than the import's duration makes
  reconciliation re-read everything changed during it.

## Assumptions

- v1 lists newest first by `updated_at`, and `updated_at` increases with every change (the mock guarantees it;
  a supplier whose timestamps go backwards breaks reconciliation's watermark).
- Deletions aren't listed. Detecting products a supplier dropped needs a full-catalog comparison: later.
