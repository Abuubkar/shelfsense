---
status: accepted
date: 2026-11-02
---

# Queued workers: per-product outcomes, explicit dead letters, heartbeats, backpressure

**The problem.** Enrichment runs a few hundred products an hour per Ollama, so it runs behind queues. Every
failure mode of bulk work happens there: a model call times out, a reply is invalid, OpenSearch rejects part of
a bulk request, a worker dies mid-batch. One bad product must not fail its batch, a crash must not lose or redo
work, and producers must slow down when the queue is full.

**Chosen.**

1. **Two SQS queues, each with a DLQ** (`enrich`, `index`; `enrich-dlq`, `index-dlq`). The redrive policy
   (`maxReceiveCount` 5) is the backstop for crashes and poison messages, not the normal failure path.
2. **One consumer loop** (`queue.consume`) for both workers: long polling, at most N messages at once, and a
   heartbeat that extends the message's visibility every third of its timeout while the handler runs. A
   `should_receive()` check stops polling when there's no capacity (the enrich worker: every model slot busy),
   so messages aren't taken and left to time out. SIGTERM stops polling and gives in-flight messages a grace
   period; anything unfinished is left unacked and comes back after its timeout.
3. **Handlers decide per product** (`plan_followups`). A message carries up to 50 product IDs. Each product ends
   done, transient (model unreachable, 5xx, timeout; bulk 429 or 5xx) or permanent (invalid output after one
   retry with the validation error shown to the model; a mapping error). Done products move on (enriched ones to
   the index queue). Transient ones go into a new message with `attempt + 1` and a jittered delay, up to 3
   attempts. Permanent ones, and transient ones out of attempts, are dead-lettered **one product per message**,
   so a redrive retries exactly the failures. Then the original message is deleted.
4. **Dead letters are recorded before they're sent.** A `dead_letters` row (queue, product, error code, detail,
   body) is committed, then the message goes to the DLQ, then `sent_at` is set. A partial unique index allows one
   open dead letter per (queue, product), so a redelivered message doesn't dead-letter a product twice.
5. **Idempotent by content.** A product is skipped when it already has a category for its current
   `content_hash`, taxonomy version and prompt version, and a category is written in the same transaction as its
   `enrichment_runs` row. So redelivery after a crash only redoes products that weren't written. Skipped products
   still count as done and are sent to indexing again: re-indexing is harmless, and it covers a crash between
   enriching and sending.
6. **Adaptive bulk indexing.** Batches start at 500 documents, halve on any 429 (whole request or item) down to
   50, and grow by 50 per clean batch up to 2,000 (AIMD). Only the items that failed are retried, up to 4 rounds
   within one message; what's left is resubmitted like enrich failures.
7. **Backpressure at the door.** `POST /v1/feeds/{id}:commit` returns 429 while the enrich queue holds more than
   `MAX_ENRICH_BACKLOG` messages (waiting, in flight or delayed). `Retry-After` is the excess divided by the
   products enriched in the last hour (`enrichment_runs`), clamped to 30 s–1 h.
8. **Model concurrency = `OLLAMA_NUM_PARALLEL`** (`LLM_MAX_CONCURRENCY`, default 1). More calls than that just
   wait inside Ollama while their messages' timeouts run.

## Alternatives

- **Let SQS's redrive handle every failure**: a whole message of 50 would be retried for one bad product, and the
  DLQ would hold batches with no recorded reason.
- **One product per message**: simplest per-item semantics, but 50x the SQS calls and no batching for the index.
- **A long visibility timeout instead of a heartbeat**: a crashed worker's messages would stay hidden that long.
- **Retry transient failures in place (sleep and call again)**: holds a model slot and the message while waiting;
  resubmitting with a delay frees both.

## Assumptions

- A product's enrichment is a pure function of its content, the taxonomy release and the prompt; re-running it
  for the same inputs is waste, not a correction.
- Index messages carry at most 50 products (one per enrich message), so adaptive sizing only matters for larger
  index requests and `scripts/sync_index.py`. Batching across messages is in docs/backlog.md.
