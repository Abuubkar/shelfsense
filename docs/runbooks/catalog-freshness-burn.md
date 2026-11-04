# Catalog freshness SLO burning

Too many products are reaching search more than 2 hours after their last change (SLO 95%, docs/slo.md).

## Look

- *Fresh within 2 h* and *Catalog freshness* on **Shelfsense / Pipeline**; then queue depth and products/hour.

## Likely causes

- An enrichment backlog (see products-per-hour-low, enrich-queue-stale).
- The index worker stalled or rejecting (*Bulk rejections*).

## Fix

- Work the cause; freshness recovers as the backlog drains. A big feed committed at once burns budget by design: check its size first.
