"""Environment configuration; secrets are required only for the features that use them."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_id: str = os.getenv("GITHUB_APP_ID", "")
    private_key_path: str = os.getenv("GITHUB_PRIVATE_KEY_PATH", "")
    webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    dashboard_token: str = os.getenv("DASHBOARD_TOKEN", "")
    db_path: str = os.getenv("DATABASE_PATH", "./repoguard.db")
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    max_pr_files: int = int(os.getenv("MAX_PR_FILES", "120"))
    max_source_files: int = int(os.getenv("MAX_REPO_SOURCE_FILES", "12"))

    @property
    def private_key(self) -> str:
        p = Path(self.private_key_path).expanduser()
        if not p.is_file():
            raise RuntimeError("GITHUB_PRIVATE_KEY_PATH is not a readable file")
        return p.read_text(encoding="utf-8")


settings = Settings()
