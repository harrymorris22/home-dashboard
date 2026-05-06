import json
from pathlib import Path

import pytest

from app.push.vapid import VapidLoadError, force_regenerate, load_or_create


def test_generate_on_miss(tmp_path: Path):
    keys = load_or_create(tmp_path / "v.json", "mailto:test@example.com")
    assert keys.subject == "mailto:test@example.com"
    assert "BEGIN PRIVATE KEY" in keys.private_pem
    assert "=" not in keys.public_b64url  # base64url no padding
    assert (tmp_path / "v.json").exists()


def test_reload_returns_same_keypair(tmp_path: Path):
    p = tmp_path / "v.json"
    a = load_or_create(p, "mailto:test@example.com")
    b = load_or_create(p, "mailto:test@example.com")
    assert a.private_pem == b.private_pem
    assert a.public_b64url == b.public_b64url


def test_corrupt_file_raises_vapid_load_error(tmp_path: Path):
    p = tmp_path / "v.json"
    p.write_text("{not valid json")
    with pytest.raises(VapidLoadError):
        load_or_create(p, "mailto:test@example.com")


def test_force_regenerate_creates_new_keypair(tmp_path: Path):
    p = tmp_path / "v.json"
    a = load_or_create(p, "mailto:test@example.com")
    b = force_regenerate(p, "mailto:test@example.com")
    assert a.private_pem != b.private_pem
    # File reflects the new keypair.
    data = json.loads(p.read_text())
    assert data["public_b64url"] == b.public_b64url
