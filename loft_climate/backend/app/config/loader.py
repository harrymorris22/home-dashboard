from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from app.config.schema import ConfigV1
from app.settings import get_settings


def load_config() -> ConfigV1:
    s = get_settings()
    if not s.config_path.exists():
        s.config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(s.config_default_path, s.config_path)
    with s.config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return ConfigV1.model_validate(data)


def save_config(cfg: ConfigV1) -> None:
    s = get_settings()
    target = s.config_path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = cfg.model_dump(mode="json")
    fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        Path(tmp_name).replace(target)
    except Exception:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except Exception:
            pass
        raise
