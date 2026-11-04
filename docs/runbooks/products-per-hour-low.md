# Products per hour under half its 24-hour average

Enrichment throughput fell below 50% of its 24-hour average while the enrich queue still holds work.

## Look

- *Products enriched / hour*, *Seconds per product* and *Model tokens* on **Shelfsense / Pipeline**.
- The slowest products' traces: click an exemplar on *Seconds per product*; the `chat <model>` span shows tokens/s.

## Likely causes

- Ollama slowed down: another model loaded alongside (the Mac is shared), memory pressure, or a bigger model configured.
- Many transient failures being resubmitted (*Products by outcome*).
- Fewer workers than usual.

## Fix

- Check `ollama ps` for other models loaded; free the GPU or wait.
- Compare tokens/s with `evals/SWEEP.md`'s numbers for the configured model.
