from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-in-production-32-chars!!"
    data_dir: Path = Path("/app/data")
    backup_retention_count: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
