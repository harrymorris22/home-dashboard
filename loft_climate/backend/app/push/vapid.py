"""VAPID keypair lifecycle.

Persists a single P-256 keypair under `/data/vapid_keys.json` for the lifetime
of the Add-on. On miss generates and saves; on parse failure HALTS the push
subsystem (does not silently regenerate — that would invalidate every iPhone
subscription with no signal to the user). The user can manually trigger
regeneration from `/notifications` once they've decided that's the right move.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

log = logging.getLogger(__name__)


class VapidLoadError(RuntimeError):
    """Raised when an existing VAPID key file is unreadable / corrupt."""


@dataclass(frozen=True)
class VapidKeys:
    private_pem: str
    public_b64url: str  # raw uncompressed point, base64url, no padding
    subject: str


def _b64url_no_pad(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _generate(subject: str) -> VapidKeys:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_key = private_key.public_key()
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return VapidKeys(
        private_pem=private_pem,
        public_b64url=_b64url_no_pad(raw),
        subject=subject,
    )


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".vapid-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        Path(tmp).replace(path)
    except Exception:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass
        raise


def load_or_create(path: Path, subject: str) -> VapidKeys:
    """Read existing keypair or generate one on miss.

    On parse failure of an existing file, raise VapidLoadError so callers can
    surface the failure to the user and offer a manual regenerate. Conservative:
    a transient FS read shouldn't silently invalidate every iPhone subscription.
    """
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return VapidKeys(
                private_pem=data["private_pem"],
                public_b64url=data["public_b64url"],
                subject=data.get("subject") or subject,
            )
        except (json.JSONDecodeError, KeyError, OSError) as e:
            log.error(
                "[push] VAPID key file at %s is corrupt or unreadable: %s. "
                "Push subsystem disabled until manually regenerated via "
                "POST /api/push/vapid/regenerate.",
                path,
                e,
            )
            raise VapidLoadError(str(e)) from e

    log.info("[push] generating VAPID keypair at %s", path)
    keys = _generate(subject)
    _atomic_write(
        path,
        {
            "private_pem": keys.private_pem,
            "public_b64url": keys.public_b64url,
            "subject": keys.subject,
        },
    )
    return keys


def force_regenerate(path: Path, subject: str) -> VapidKeys:
    """Explicit user action: replace the existing keypair.

    Side effect: every existing PushSubscription becomes invalid; dispatcher
    will see 403/410 on next push and prune them. The user must re-grant
    notification permission per device after this.
    """
    log.warning("[push] regenerating VAPID keypair on user request at %s", path)
    keys = _generate(subject)
    _atomic_write(
        path,
        {
            "private_pem": keys.private_pem,
            "public_b64url": keys.public_b64url,
            "subject": keys.subject,
        },
    )
    return keys
