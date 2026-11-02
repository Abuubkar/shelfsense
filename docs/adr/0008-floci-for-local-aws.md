---
status: accepted
date: 2026-11-02
---

# Floci for local SQS and S3, not LocalStack

**Chosen.** `floci/floci:2.3.0` in docker-compose on `127.0.0.1:4566`, storage mode `persistent` (queues,
messages and uploaded feeds survive a restart). Service tests start the same image in memory mode. The code
talks to it with aioboto3 15.5 through `aws.py`; pointing `AWS_ENDPOINT_URL` elsewhere (empty = real AWS) is the
only change needed. The bucket and queues are created by `scripts/init_aws.py` (`aws.ensure_resources`), not by
emulator init hooks, so the same code sets up the service-test containers.

**Why not LocalStack, which the plan names.** Since LocalStack 2026.03.0 the image won't start without an account
auth token; the free tier is for non-commercial use and needs an account per developer and for CI. Floci is
MIT-licensed, needs no account or token, starts in under a second, and covers what slice 3 uses.

**Measured on 2.3.0** before building on it (docs/challenges.md): `ApproximateReceiveCount` counts receives; a
message received 5 times without a delete moves to the DLQ by its redrive policy; `StartMessageMoveTask` moves
DLQ messages back and refuses a second concurrent task (`InvalidParameterValue`, "already a task running");
presigned SigV4 PUTs work; a missing object is `NoSuchKey`.

## Alternatives

- **LocalStack with a Hobby token**: the reference emulator, but an account per person and per CI runner.
- **ElasticMQ (SQS) + an S3 server**: two containers, and ElasticMQ has no message move tasks, so redrive would
  be our own receive-and-resend loop.
- **moto server**: one container, but no `StartMessageMoveTask`.

## Assumptions

- Floci's SQS semantics match AWS for what we use (visibility, receive counts, redrive, move tasks). Anything we
  rely on beyond that gets a probe first. Real AWS remains the reference; slice 7's CI runs the same Floci image.
- Floci is young (monthly releases). We pin an exact version and upgrade deliberately.
