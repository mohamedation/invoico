from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_host: str = "http://127.0.0.1:11434"
    model: str = "gemma3:4b"
    data_dir: Path = ROOT / "data"
    db_path: Path = ROOT / "data" / "invoices.db"
    upload_dir: Path = ROOT / "data" / "uploads"
    max_pdf_pages: int = 3
    max_image_width: int = 1280
    api_base: str = "http://127.0.0.1:8000"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
