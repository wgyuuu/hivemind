"""Configuration loading and validation.

Precedence (low -> high):
    code defaults  <  config/hivemind.toml  <  config/hivemind.local.toml
                   <  env vars  <  .env

Secrets (DingTalk client id/secret) only ever come from env / .env — never from
any committed .toml file. The toml layers are merged in via a custom
pydantic-settings source so nested models (monitor/hooks/router) deep-merge
correctly.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

try:  # py311+ has tomllib in stdlib
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


# Project root = two levels up from this file (src/hivemind/config.py -> project/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


class DingTalkSettings(BaseModel):
    client_id: str = ""
    client_secret: str = ""


class HooksSettings(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8787


class MonitorSettings(BaseModel):
    poll_interval_sec: float = 2.0
    capture_lines: int = 200


class RouterSettings(BaseModel):
    address_prefix: str = "@"
    command_prefix: str = "/"


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base`, returning a new dict."""
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


class TomlConfigSource(PydanticBaseSettingsSource):
    """pydantic-settings source that injects merged toml layers.

    hivemind.toml (committed defaults) is overlaid by hivemind.local.toml
    (gitignored machine overrides). Env / .env still win over both.
    """

    def get_field_value(self, field, field_name):  # noqa: D102 (abstract)
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        base = _load_toml(CONFIG_DIR / "hivemind.toml")
        local = _load_toml(CONFIG_DIR / "hivemind.local.toml")
        merged = _deep_merge(base, local)
        # Map flat [router]/[monitor]/[hooks] tables onto the nested models.
        return {k: v for k, v in merged.items() if isinstance(v, dict)}


class Settings(BaseSettings):
    """Top-level settings.

    Env vars use the nested delimiter, e.g. HIVEMIND_DINGTALK__CLIENT_ID.
    """

    model_config = SettingsConfigDict(
        env_prefix="HIVEMIND_",
        env_nested_delimiter="__",
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    dingtalk: DingTalkSettings = Field(default_factory=DingTalkSettings)
    hooks: HooksSettings = Field(default_factory=HooksSettings)
    monitor: MonitorSettings = Field(default_factory=MonitorSettings)
    router: RouterSettings = Field(default_factory=RouterSettings)

    var_dir: Path = PROJECT_ROOT / "var"
    log_level: str = "INFO"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Order = precedence (first wins). toml sits below env/.env.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSource(settings_cls),
            file_secret_settings,
        )

    def ensure_runtime_dirs(self) -> None:
        """Create var/{logs,run,state} so the daemon can write immediately."""
        for sub in ("logs", "run", "state"):
            (self.var_dir / sub).mkdir(parents=True, exist_ok=True)

    @property
    def terminals_toml(self) -> Path:
        return CONFIG_DIR / "terminals.toml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build the singleton Settings, merging toml layers then env/.env."""
    settings = Settings()
    if "HIVEMIND_VAR_DIR" in os.environ:
        settings.var_dir = Path(os.environ["HIVEMIND_VAR_DIR"])
    return settings


def load_settings() -> Settings:
    """Public entry used by the Bridge. Alias for the cached get_settings()."""
    return get_settings()
