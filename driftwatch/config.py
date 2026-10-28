"""
Central configuration.

Concept: never hard-code connection details or secrets in code. They live in a
.env file locally, and later in Kubernetes Secrets / ConfigMaps. The code only
reads environment variables, so the same code runs on your laptop, in Docker,
and in Kubernetes without changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    sql_server: str = field(default_factory=lambda: _env("DW_SQL_SERVER", "localhost"))
    sql_database: str = field(default_factory=lambda: _env("DW_SQL_DATABASE", "DriftwatchSource"))
    sql_driver: str = field(default_factory=lambda: _env("DW_SQL_DRIVER", "ODBC Driver 18 for SQL Server"))
    sql_trusted: bool = field(default_factory=lambda: _env("DW_SQL_TRUSTED", "yes").lower() in ("yes", "true", "1"))
    sql_user: str = field(default_factory=lambda: _env("DW_SQL_USER"))
    sql_password: str = field(default_factory=lambda: _env("DW_SQL_PASSWORD"))

    tables: tuple[str, ...] = field(
        default_factory=lambda: tuple(t.strip() for t in _env("DW_TABLES", "customers,products,orders").split(",") if t.strip())
    )
    chunk_size: int = field(default_factory=lambda: int(_env("DW_CHUNK_SIZE", "5000")))
    max_retries: int = field(default_factory=lambda: int(_env("DW_MAX_RETRIES", "3")))

    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def lake_dir(self) -> Path:
        """Destination: our home-made data lake of Parquet snapshots."""
        return self.data_dir / "lake"

    @property
    def metadata_db(self) -> Path:
        """DuckDB file that records every pipeline run."""
        return self.data_dir / "metadata.duckdb"

    @property
    def alerts_log(self) -> Path:
        return self.data_dir / "alerts.log"

    def odbc_connection_string(self) -> str:
        parts = [
            f"DRIVER={{{self.sql_driver}}}",
            f"SERVER={self.sql_server}",
            f"DATABASE={self.sql_database}",
            # Driver 18 encrypts by default; a local dev server uses a self-signed
            # certificate, so we trust it. In production you'd use a real certificate.
            "Encrypt=yes",
            "TrustServerCertificate=yes",
        ]
        if self.sql_trusted:
            parts.append("Trusted_Connection=yes")
        else:
            parts.append(f"UID={self.sql_user}")
            parts.append(f"PWD={self.sql_password}")
        return ";".join(parts) + ";"

    def sqlalchemy_url(self) -> str:
        return "mssql+pyodbc:///?odbc_connect=" + quote_plus(self.odbc_connection_string())


settings = Settings()