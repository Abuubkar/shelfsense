# DLQ depth over 100

A dead-letter queue (`enrich-dlq` or `index-dlq`) holds more than 100 messages: products that failed permanently, each with its reason in `dead_letters`.

## Look

- Grafana **Shelfsense / Pipeline**, *DLQ depth* and *Products by outcome* (a rise in `permanent`).
- The reasons: `SELECT error_code, count(*) FROM dead_letters WHERE redriven_at IS NULL GROUP BY 1 ORDER BY 2 DESC;`
- A sample trace: Jaeger keeps every DLQ send (`shelfsense.dlq=true`); `uv run python scripts/trace_tree.py --product <id>` for one of them.

## Likely causes

- `invalid_model_output` after its retry: a prompt or model change the grammar fights (docs/challenges.md).
- `mapper_parsing_exception` on the index DLQ: a mapping change shipped without a new index version (ADR 0019).
- `prompt_truncated`: listings longer than `LLM_NUM_CTX` allows.

## Fix

- Fix the cause first, then redrive: dry run `curl -X POST localhost:8020/v1/admin/dlq/enrich/redrive -H 'content-type: application/json' -d '{}'`, then with `{"dry_run": false}`.
- A redrive puts the products back on the work queue; the alert clears as the DLQ drains.
