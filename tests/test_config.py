"""Config reads .env by hand (no python-dotenv dependency), so the quoting
rules that file format allows have to be handled here."""
import os

from houston.config import Config, _load_dotenv


def test_quoted_values_lose_their_quotes(tmp_path, monkeypatch):
    """`DD_SITE="datadoghq.com"` is valid .env syntax, and keeping the
    quotes produced `https://api."datadoghq.com"` on every request."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        'DD_API_KEY="abc123"\n'
        "DD_APP_KEY='def456'\n"
        'DD_SITE="datadoghq.com"\n'
    )
    for key in ("DD_API_KEY", "DD_APP_KEY", "DD_SITE"):
        monkeypatch.delenv(key, raising=False)

    _load_dotenv(env_file)

    assert os.environ["DD_SITE"] == "datadoghq.com"
    assert Config.from_env().base_url == "https://api.datadoghq.com"
    assert os.environ["DD_API_KEY"] == "abc123"
    assert os.environ["DD_APP_KEY"] == "def456"


def test_unquoted_values_are_unchanged(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DD_SITE=us5.datadoghq.com\n")
    monkeypatch.delenv("DD_SITE", raising=False)

    _load_dotenv(env_file)

    assert os.environ["DD_SITE"] == "us5.datadoghq.com"


def test_missing_credentials_raise_instead_of_silently_calling_datadog(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "")
    monkeypatch.setenv("DD_APP_KEY", "")
    try:
        Config.from_env()
    except RuntimeError as exc:
        assert "DD_API_KEY" in str(exc)
    else:
        raise AssertionError("expected a RuntimeError")
