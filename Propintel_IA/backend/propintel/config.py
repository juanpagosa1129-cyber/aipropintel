from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_path: Path
    frontend_dir: Path
    import_dir: Path
    rama_judicial_base_url: str
    request_timeout_seconds: int
    crawler_user_agent: str

    @classmethod
    def from_env(cls, root: Path) -> "Settings":
        database_path = Path(os.getenv("DATABASE_PATH", root / "data" / "propintel.sqlite3"))
        frontend_dir = Path(os.getenv("FRONTEND_DIR", root / "frontend"))
        import_dir = Path(os.getenv("IMPORT_DIR", root / "data" / "imports"))
        return cls(
            host=os.getenv("APP_HOST", "127.0.0.1"),
            port=int(os.getenv("APP_PORT", "8088")),
            database_path=database_path if database_path.is_absolute() else root / database_path,
            frontend_dir=frontend_dir if frontend_dir.is_absolute() else root / frontend_dir,
            import_dir=import_dir if import_dir.is_absolute() else root / import_dir,
            rama_judicial_base_url=os.getenv("RAMA_JUDICIAL_BASE_URL", ""),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "25")),
            crawler_user_agent=os.getenv("CRAWLER_USER_AGENT", "PropintelIA/1.0"),
        )
