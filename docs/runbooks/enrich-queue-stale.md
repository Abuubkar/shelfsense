# Enrich queue messages waiting over 6 hours

Messages in the enrich queue waited more than 6 hours before a worker received them, or the queue holds messages and none has been received for 6 hours.

## Look

- *Queue depth* and *Message wait before receive* on **Shelfsense / Pipeline**; *Model calls in flight* (stuck at the cap?).
- Are enrich workers running? `ps aux | grep shelfsense_worker_enrich`; their JSON logs on stderr, or in Loki: `{service_name="shelfsense-worker-enrich"}`.
- SQS age isn't in GetQueueAttributes (it's a CloudWatch metric), so the wait is measured at receive: a worker that receives nothing reports nothing, hence the second condition.

## Likely causes

- No enrich worker running, or all of them blocked on Ollama (see the Ollama alert).
- A feed larger than the workers' throughput: products/hour × 6 h is the backlog a 6-hour wait means.

## Fix

- Start or scale workers (one per Ollama; `LLM_MAX_CONCURRENCY` = `OLLAMA_NUM_PARALLEL`).
- Feed commits already refuse new work over `MAX_ENRICH_BACKLOG` (409 with a retry time); lower it if the backlog keeps outgrowing 6 hours.
