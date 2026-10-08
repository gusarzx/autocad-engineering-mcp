"""Bounded file access and conservative DWG overwrite policy."""

import shutil
from pathlib import Path
from uuid import uuid4

from .exceptions import CadError


class FilePolicy:
    """Restrict local drawing/library paths to the configured root."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def resolve(self, name: str, suffix: str = ".dwg") -> Path:
        if len(name) > 1024 or "\x00" in name:
            raise CadError("Invalid file path")
        candidate = Path(name).expanduser()
        path = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        if not path.is_relative_to(self.root) or path.suffix.lower() != suffix:
            raise CadError(f"Path must remain inside save_root and end with {suffix}")
        if ":" in path.name or path.name.upper().split(".")[0] in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"COM{i}" for i in range(1, 10)],
            *[f"LPT{i}" for i in range(1, 10)],
        }:
            raise CadError("Reserved Windows filename")
        return path

    def prepare_save(self, name: str, overwrite: bool) -> tuple[Path, Path | None]:
        path = self.resolve(name)
        backup = None
        if path.exists():
            if not overwrite:
                raise CadError("DWG already exists; explicit overwrite=true required")
            backup = path.with_name(f"{path.stem}.{uuid4().hex}.bak")
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path, backup
