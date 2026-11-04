# Ollama unreachable for 2 minutes

The enrich worker's probe of `OLLAMA_HOST/api/version` has failed for 2 minutes.

## Look

- `curl -s $OLLAMA_HOST/api/version`; `ollama ps`.
- *Ollama* on **Shelfsense / Pipeline**.

## Likely causes

- Ollama stopped or crashed (it runs natively on the Mac, not in Docker).
- `OLLAMA_HOST` points at the wrong place.

## Fix

- Restart Ollama. Messages already received fail as `model_unavailable` (transient) and are resubmitted with backoff; nothing is lost.
- Search keeps working: the query model degrades to keywords (ADR 0014).
