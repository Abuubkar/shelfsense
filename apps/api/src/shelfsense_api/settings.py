from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://shelfsense:shelfsense@localhost:5436/shelfsense"

    # The Google Product Taxonomy release products are classified into (data/taxonomy/<version>.txt).
    taxonomy_version: str = "2021-09-21"
    # Leaves the embedding pre-filter hands the model; the right leaf must be among them (candidate recall).
    candidate_count: int = 15

    # Ollama runs natively on the host: Docker on macOS has no GPU access.
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_temperature: float = 0.0
    # Always sent explicitly: Ollama's default context is small and truncates long prompts silently.
    llm_num_ctx: int = 4096
    llm_keep_alive: str = "10m"
    llm_timeout_s: float = 120.0


settings = Settings()
