from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://shelfsense:shelfsense@localhost:5436/shelfsense"

    # The Google Product Taxonomy release products are classified into (data/taxonomy/<version>.txt).
    taxonomy_version: str = "2021-09-21"
    # Leaves the embedding pre-filter hands the model; the right leaf must be among them (candidate recall).
    candidate_count: int = 15

    # OpenSearch serves search; it's rebuilt from Postgres, never the other way round.
    opensearch_url: str = "http://localhost:9201"
    # How long an idle search cursor stays valid. Each page renews it.
    search_cursor_ttl: str = "5m"
    # A product counts as a semantic match when its k-NN score is at least this. For cosine, OpenSearch scores
    # (1 + cos) / 2, so 0.80 is cos 0.6 (docs/adr/0006).
    knn_min_score: float = 0.80
    # Weights of the BM25 and k-NN scores after min-max normalization, in that order.
    hybrid_weights: tuple[float, float] = (0.5, 0.5)
    # Signs pagination cursors so clients can't forge or edit them. Override in every real deployment.
    cursor_secret: str = "dev-only-cursor-secret"

    # Ollama runs natively on the host: Docker on macOS has no GPU access.
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_temperature: float = 0.0
    # Always sent explicitly: Ollama's default context is small and truncates long prompts silently.
    llm_num_ctx: int = 4096
    llm_keep_alive: str = "10m"
    llm_timeout_s: float = 120.0
    # Model calls one enrich worker runs at once. Match OLLAMA_NUM_PARALLEL (Ollama's default is 1): Ollama queues
    # anything beyond it, so more only burns visibility-timeout time.
    llm_max_concurrency: int = 1

    # SQS and S3. Locally that's Floci (docs/adr/0008); leave aws_endpoint_url empty for real AWS.
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    feeds_bucket: str = "feeds"
    # How long a presigned feed upload URL stays valid.
    feed_upload_expiry_s: int = 900
    enrich_queue: str = "enrich"
    index_queue: str = "index"
    # Product IDs per enrich message: small enough that one message's model calls finish in minutes.
    enrich_batch_size: int = 50
    # Feed commits are refused (429) while the enrich queue holds more messages than this: 4,000 x 50 is
    # 200k products, days of work for one Ollama.
    max_enrich_backlog: int = 4000
    # Attempts per product for transient failures (model unreachable, 5xx, timeout, bulk rejections), counting
    # the first. After the last one the product is dead-lettered.
    max_attempts: int = 3
    # A received message stays hidden this long; the consumer extends it every third of it while working.
    queue_visibility_timeout_s: int = 60
    # Long-poll wait per receive. Also bounds how long a worker takes to notice a shutdown request.
    queue_wait_s: int = 10
    # Messages one worker handles at once.
    enrich_message_concurrency: int = 2
    index_message_concurrency: int = 4
    # On SIGTERM, how long in-flight messages get to finish before the worker exits without acking them.
    worker_shutdown_grace_s: float = 30.0


settings = Settings()
