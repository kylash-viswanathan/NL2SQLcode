"""Central config: loads .env and exposes typed settings. No secrets are hardcoded."""
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
SENSITIVITY_TAGS_PATH = REPO_ROOT / "config" / "sensitivity_tags.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str
    generation_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    turso_database_url: str
    turso_auth_token: str

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    chroma_persist_dir: str = "./chroma_db"

    max_self_heal_retries: int = 2


settings = Settings()


def load_sensitivity_tags() -> dict[str, dict[str, str]]:
    """table -> {column -> tag}, tag in {PII, confidential, public}."""
    with open(SENSITIVITY_TAGS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def mask_columns(tags: dict[str, dict[str, str]] | None = None) -> set[tuple[str, str]]:
    """(table, column) pairs tagged PII — always masked by governance, regardless of HITL outcome."""
    tags = tags or load_sensitivity_tags()
    return {
        (table, column)
        for table, columns in tags.items()
        for column, tag in columns.items()
        if tag == "PII"
    }


def hitl_trigger_columns(tags: dict[str, dict[str, str]] | None = None) -> set[tuple[str, str]]:
    """(table, column) pairs that require human approval before execution: PII + confidential."""
    tags = tags or load_sensitivity_tags()
    return {
        (table, column)
        for table, columns in tags.items()
        for column, tag in columns.items()
        if tag in ("PII", "confidential")
    }
