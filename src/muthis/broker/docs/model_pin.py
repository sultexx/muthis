# src/muthis/broker/docs/model_pin.py
"""
The encoder artifact, PINNED BY FINGERPRINT with a spoken first-download.

THE DEC-3-D PATTERN, applied to a model instead of a container image. That
ruling pinned the sandbox image by sha256 and required a SPOKEN first-pull, for
two reasons that transfer exactly: a silently-swapped artifact is a supply-chain
hole, and a multi-second first-run download with no voice is indistinguishable
from a hang.

WHY THE FINGERPRINT IS LOAD-BEARING HERE SPECIFICALLY (DEC-44): the encoder is
the one component whose corruption is INVISIBLE. A wrong parser raises, a wrong
tokenizer produces nonsense — but a substituted encoder returns vectors of the
right shape and the right dtype, and every downstream stage looks healthy while
retrieval quality quietly collapses. There is no runtime signal. The fingerprint
IS the signal.

WHY THIS MODEL AND NOT `bge-m3` (DEC-49 ruling 2, from the P0 gate): bge-m3 was
disqualified on THREE stated conditions, and the first one lands here — it ships
NO publisher int8 artifact at all, so DEC-44's pinning clause cannot reach it.
Any int8 bge-m3 would pin our own build or a stranger's re-upload, never the
publisher's. `multilingual-e5-small` ships a publisher-built int8, which is what
makes the line below a real pin rather than a hash of something we made.

THE HASHES BELOW WERE MEASURED, never recalled: computed at T2 over the exact
files the P0 gate benchmarked.

Pure stdlib. `huggingface_hub` is lazy-imported inside the download path ONLY,
so a machine with the model already present never loads it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import pathlib
from typing import Callable, Optional

logger = logging.getLogger("muthis.broker.docs")

# The announce seam (DEC-3-D). Defaults to the LOGGER, exactly as `McpHost`'s
# three-strikes announcement does in Phase 1: the seam exists and is tested, and
# the audible delivery joins the voice line with its consumer. Wiring audio here
# would touch the sacred path for a component that has no user-facing turn yet.
AnnounceFn = Callable[[str], None]

# Arabic, because it is the ONLY string in this module a user ever hears — the
# language-split law: user surfaces Arabic, logs English.
FIRST_DOWNLOAD_AR = "أحمّل نموذج فهم المستندات لأول مرة — دقيقة تقريبًا."


class ModelFingerprintMismatch(Exception):
    """A pinned file's sha256 did not match. FAIL CLOSED, always.

    Never downgraded to a warning: the whole point of the pin is that this is the
    only moment a substitution is detectable."""


@dataclasses.dataclass(frozen=True)
class ModelPin:
    """One pinned artifact set: what to fetch, and what it must hash to."""

    repo: str
    files: dict[str, str]              # repo-relative path -> sha256
    dim: int
    max_sequence: int

    def local_name(self, repo_path: str) -> str:
        """The flat on-disk name — the basename, so the cache has no nesting."""
        return repo_path.rsplit("/", 1)[-1]


# `intfloat/multilingual-e5-small`, the PUBLISHER-BUILT int8 ONNX export.
# Chosen by measurement at the P0 gate (DEC-49 ruling 2): 118 MB, 30.6 ms median
# per chunk, 76% hit@5 — against bge-m3's 19x disk, 18x latency and no int8.
E5_SMALL_INT8 = ModelPin(
    repo="intfloat/multilingual-e5-small",
    files={
        "onnx/model_qint8_avx512_vnni.onnx":
            "dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88",
        "tokenizer.json":
            "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
        "config.json":
            "69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959",
    },
    dim=384,
    max_sequence=512,
)


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:                # streamed: the ONNX is 118 MB
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(directory: pathlib.Path, pin: ModelPin = E5_SMALL_INT8) -> list[str]:
    """Which pinned files are MISSING from `directory`. Present-but-wrong RAISES.

    The two outcomes are deliberately different: missing is an ordinary first
    run, wrong is a supply-chain event. Collapsing them into one "re-download"
    path would let a tampered file be silently replaced and never reported."""
    missing: list[str] = []
    checked = 0
    for repo_path, expected in pin.files.items():
        local = directory / pin.local_name(repo_path)
        if not local.exists():
            missing.append(repo_path)
            continue
        actual = _sha256(local)
        checked += 1
        if actual != expected:
            raise ModelFingerprintMismatch(
                f"{local.name}: expected {expected[:16]}… got {actual[:16]}…")
    logger.info("[doc_rag] model pin: verified=%d missing=%d of %d pinned files",
                checked, len(missing), len(pin.files))
    return missing


def ensure_model(
    directory: pathlib.Path,
    *,
    pin: ModelPin = E5_SMALL_INT8,
    announce: Optional[AnnounceFn] = None,
    allow_download: bool = True,
) -> pathlib.Path:
    """Return `directory` with every pinned file present and hash-verified.

    Announces BEFORE the first download, never after — the point of DEC-3-D is
    that the user learns why the machine went quiet while it is quiet.

    `allow_download=False` is the offline posture: it raises rather than reaching
    the network, so a caller that must not touch the network can prove it."""
    missing = verify(directory, pin)
    if not missing:
        return directory
    if not allow_download:
        raise FileNotFoundError(
            f"model artifacts missing and downloads disabled: {missing}")

    (announce or _log_announce)(FIRST_DOWNLOAD_AR)
    logger.info("[doc_rag] downloading %d pinned file(s) from %s",
                len(missing), pin.repo)
    from huggingface_hub import hf_hub_download   # lazy: only the first run pays

    directory.mkdir(parents=True, exist_ok=True)
    for repo_path in missing:
        source = pathlib.Path(hf_hub_download(pin.repo, repo_path))
        (directory / pin.local_name(repo_path)).write_bytes(source.read_bytes())

    still_missing = verify(directory, pin)          # re-verify: hashes included
    if still_missing:
        raise FileNotFoundError(f"download did not produce: {still_missing}")
    return directory


def _log_announce(text_ar: str) -> None:
    """The default seam. English log line ABOUT an Arabic user string — the two
    surfaces never mix, so the log states the event, not the sentence."""
    logger.info("[doc_rag] first model download starting (announce seam unwired)")


__all__ = [
    "AnnounceFn", "E5_SMALL_INT8", "FIRST_DOWNLOAD_AR",
    "ModelFingerprintMismatch", "ModelPin", "ensure_model", "verify",
]
