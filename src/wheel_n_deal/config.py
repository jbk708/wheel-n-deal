import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

HttpUrlStr = Annotated[str, StringConstraints(pattern=r"^https?://\S+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WatchItem(StrictModel):
    url: HttpUrlStr
    name: str
    target_price: float = Field(gt=0)
    notes: str | None = None


class NtfyConfig(StrictModel):
    url: HttpUrlStr
    topic: str = "deals"


class LLMConfig(StrictModel):
    base_url: HttpUrlStr
    model: str = "mimo-v2.6-flash"


class PolitenessConfig(StrictModel):
    min_interval_hours: float = Field(default=6, gt=0)
    jitter_minutes: float = Field(default=30, ge=0)


class FetchConfig(StrictModel):
    # Shop page fetches only (plain and headless); our own services always go direct.
    proxy_url: HttpUrlStr | None = None


class Config(StrictModel):
    watch: list[WatchItem] = []
    ntfy: NtfyConfig
    llm: LLMConfig
    politeness: PolitenessConfig = PolitenessConfig()
    fetch: FetchConfig = FetchConfig()
    data_dir: Path = Path("/data")
    heartbeat_url: HttpUrlStr | None = None

    @model_validator(mode="after")
    def _unique_urls(self) -> "Config":
        urls = [item.url for item in self.watch]
        if len(urls) != len(set(urls)):
            raise ValueError("duplicate url in watch list")
        return self


@dataclass(frozen=True)
class Secrets:
    llm_api_key: str | None = field(repr=False)
    ntfy_token: str | None = field(repr=False)
    api_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Secrets":
        return cls(
            llm_api_key=env.get("LLM_API_KEY") or None,
            ntfy_token=env.get("NTFY_TOKEN") or None,
            api_token=env.get("WND_API_TOKEN") or None,
        )


def load_config(path: Path | str) -> Config:
    with open(path) as f:
        return Config.model_validate(yaml.safe_load(f))
