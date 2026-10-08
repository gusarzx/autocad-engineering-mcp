"""Environment configuration and project-defined drafting profiles."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(BaseModel):
    """Illustrative conventions, not certified GOST/SPDS symbols."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    layers: dict[str, int] = Field(
        default_factory=lambda: {
            "HVAC_DUCT": 4,
            "HVAC_EQUIPMENT": 3,
            "PLUMBING_PIPE": 5,
            "PLUMBING_EQUIPMENT": 2,
            "TEXT": 7,
            "DIMENSIONS": 7,
            "BUILDING": 8,
            "AXES": 1,
        }
    )
    linetype: str = "Continuous"
    text_height: float = Field(default=150, gt=0, le=1e6)
    symbol_scale: float = Field(default=1, gt=0, le=1000)
    layer_names: dict[str, str] = Field(default_factory=dict)
    symbols: dict[str, str] = Field(default_factory=dict)

    @field_validator("layers")
    @classmethod
    def valid_colors(cls, value):
        if len(value) > 100 or any(not 1 <= color <= 255 for color in value.values()):
            raise ValueError("Profile requires at most 100 layers with colours 1..255")
        return value

    @field_validator("layer_names")
    @classmethod
    def valid_names(cls, value):
        from pydantic import TypeAdapter

        from .core.models import Name

        for name in value.values():
            TypeAdapter(Name).validate_python(name)
        return value

    def layer(self, role: str) -> str:
        """Resolve a semantic role to a project-defined layer name."""
        return self.layer_names.get(role, role)


class Settings(BaseSettings):
    """No automatic loading of credentials or .env files."""

    model_config = SettingsConfigDict(env_prefix="ACAD_MCP_", extra="forbid")
    backend: Literal["com", "mock"] = "com"
    save_root: Path = Field(
        default_factory=lambda: Path.home() / "Documents" / "AutoCAD Engineering MCP"
    )
    prog_id: str = "AutoCAD.Application.26"
    expected_version: str = "26.0"
    max_batch: int = Field(default=100, ge=1, le=500)
    max_change: int = Field(default=20, ge=1, le=1000)
    page_size: int = Field(default=100, ge=1, le=500)
    scan_limit: int = Field(default=10000, ge=1, le=100000)
    profile: Path | None = None

    def drafting_profile(self) -> Profile:
        """Load an optional explicit JSON profile."""
        if self.profile is None:
            return Profile()
        if self.profile.stat().st_size > 100_000:
            raise ValueError("Profile exceeds 100 KB")
        return Profile.model_validate(json.loads(self.profile.read_text(encoding="utf-8")))
