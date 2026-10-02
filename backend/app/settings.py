from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DROPZERO_", env_file=REPO_ROOT / ".env", extra="ignore"
    )

    data_dir: Path = REPO_ROOT / "var"
    config_dir: Path = REPO_ROOT / "config"
    media_key: str = ""  # base64 32 bytes; required for any upload
    media_retention_hours: float = 72
    ffmpeg: str = ""
    ffprobe: str = ""
    asr_device: Literal["auto", "cuda", "cpu"] = "auto"
    embed_device: Literal["auto", "cuda", "cpu"] = "auto"

    def resolved_data_dir(self) -> Path:
        d = self.data_dir if self.data_dir.is_absolute() else REPO_ROOT / self.data_dir
        return d

    @property
    def db_path(self) -> Path:
        return self.resolved_data_dir() / "dropzero.db"

    @property
    def media_dir(self) -> Path:
        return self.resolved_data_dir() / "media"

    @property
    def work_dir(self) -> Path:
        return self.resolved_data_dir() / "work"

    @property
    def cache_dir(self) -> Path:
        return self.resolved_data_dir() / "cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
