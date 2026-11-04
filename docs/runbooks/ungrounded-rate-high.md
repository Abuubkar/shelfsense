# Ungrounded attribute rate over 6%

More than 6% of the attributes the model proposed in the last hour had no evidence span in the listing and were dropped (ADR 0015).

## Look

- *Attributes by result* and *Ungrounded ratio* on **Shelfsense / Pipeline**.
- Recent runs: `SELECT model, prompt_version, sum(ungrounded_attributes)::float / nullif(sum(ungrounded_attributes + coalesce(unnormalized_attributes,0)),0) FROM enrichment_runs WHERE created_at > now() - interval '1 hour' GROUP BY 1, 2;`
- `uv run python scripts/attributes_report.py --sample 20` shows evidence per attribute.

## Likely causes

- A model or prompt change (the 6b sweep: llama3.1:8b ran at 7.2% against qwen2.5:7b's 4.6%).
- A supplier's feed with values in columns the prompt doesn't show.

## Fix

- Roll back the model or prompt change, then `make eval LIVE=1` (when Ollama is free) before trying again.
