# Fast-path latency SLO burning

Too many first-page fast-path searches are over 150 ms (SLO 95%, docs/slo.md).

## Look

- As for fast-path-slow: *Latency by parse path*, then a slow search's trace.

## Likely causes

- As for fast-path-slow.

## Fix

- As for fast-path-slow. A sustained burn after a deploy points at the deploy: compare `make perf-smoke` before and after.
