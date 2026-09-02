"""Environment configuration, loaded from .env (never committed)."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # `DD_SITE="datadoghq.com"` is valid .env syntax; keeping the quotes
        # produced `https://api."datadoghq.com"` on every request.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    dd_api_key: str
    dd_app_key: str
    dd_site: str

    @property
    def base_url(self) -> str:
        return f"https://api.{self.dd_site}"

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.environ.get("DD_API_KEY", "")
        app_key = os.environ.get("DD_APP_KEY", "")
        site = os.environ.get("DD_SITE", "datadoghq.com")
        if not api_key or not app_key:
            raise RuntimeError(
                "DD_API_KEY / DD_APP_KEY missing — copy .env.example to .env "
                "and fill in read-scoped Datadog credentials (see ADR-0003 / "
                "docs/e0-verification.md)."
            )
        return cls(dd_api_key=api_key, dd_app_key=app_key, dd_site=site)
