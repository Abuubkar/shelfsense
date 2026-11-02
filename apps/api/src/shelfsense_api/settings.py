from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://shelfsense:shelfsense@localhost:5436/shelfsense"

    # POST /v1/feeds:import-local only reads files under this directory.
    feeds_dir: str = "data/feeds"

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


settings = Settings()
