"""The write-once evidence store (docs/case-management/04 §3.2 and 07 §2).

Every file is kept once, under its SHA-256: `objects/ab/cd/<sha256>`. The application never rewrites,
renames or removes a stored object:
- a new object is put in place with a hard link, which fails if the name already exists, so nothing is
  ever overwritten; it is then made read-only;
- an object that already exists is re-hashed before it is reused, so a damaged copy is noticed;
- uploads that are refused never reach the store (they wait in `incoming/` and are removed from there).

This protects against the application and its users. Against someone with administrator access to the
server it only *detects* changes (integrity checks recompute the hashes). Real write-once storage, such as
S3 Object Lock in compliance mode, is the production option behind the same interface (decision D14).
"""

import hashlib
import os
import re
import shutil
import stat
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Protocol

from app.casemgmt.errors import Conflict, Invalid, TooLarge
from app.casemgmt.filetypes import HEAD_BYTES
from app.core.config import get_settings

CHUNK = 1024 * 1024
KEY = re.compile(r"^objects/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$")


@dataclass
class Incoming:
    """An upload received and hashed, waiting to be accepted (keep) or refused (discard)."""

    path: Path
    sha256: str
    size: int
    head: bytes  # the first bytes, for the file-type check


class EvidenceStore(Protocol):
    backend: str

    def receive(self, stream: BinaryIO, max_bytes: int) -> Incoming: ...
    def keep(self, incoming: Incoming) -> tuple[str, bool]: ...
    def discard(self, incoming: Incoming) -> None: ...
    def chunks(self, key: str) -> Iterator[bytes]: ...
    def local_path(self, key: str) -> Path: ...
    def hash(self, key: str) -> str | None: ...


def key_for(sha256: str) -> str:
    return f"objects/{sha256[:2]}/{sha256[2:4]}/{sha256}"


class LocalEvidenceStore:
    """A folder on this server. For development and small installations; see the module docstring."""

    backend = "local"

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if not KEY.fullmatch(key):
            raise ValueError(f"Not an evidence object key: {key!r}")
        return self.root / key

    def receive(self, stream: BinaryIO, max_bytes: int) -> Incoming:
        """Copy an upload to `incoming/`, hashing it on the way. Over the limit or empty: refused, nothing kept."""
        folder = self.root / "incoming"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex}.part"
        digest, size, head = hashlib.sha256(), 0, b""
        try:
            with path.open("xb") as out:
                while block := stream.read(CHUNK):
                    size += len(block)
                    if size > max_bytes:
                        raise TooLarge(f"The file is larger than the limit of {max_bytes // (1024 * 1024)} MB")
                    if len(head) < HEAD_BYTES:
                        head += block[:HEAD_BYTES - len(head)]
                    digest.update(block)
                    out.write(block)
            if size == 0:
                raise Invalid("The file is empty")
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return Incoming(path, digest.hexdigest(), size, head)

    def discard(self, incoming: Incoming) -> None:
        incoming.path.unlink(missing_ok=True)

    def keep(self, incoming: Incoming) -> tuple[str, bool]:
        """Put an upload in the store under its hash. Returns (key, newly stored?). Never overwrites."""
        key = key_for(incoming.sha256)
        final = self._path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        try:
            try:
                os.link(incoming.path, final)  # fails if the name exists: an object is never replaced
                created = True
            except FileExistsError:
                created = False
            except OSError:  # a file system without hard links: copy into a file that must not exist yet
                created = self._copy_exclusive(incoming.path, final)
        finally:
            self.discard(incoming)
        if created:
            os.chmod(final, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        elif self.hash(key) != incoming.sha256:
            raise Conflict("A stored copy of this file exists but no longer matches its fingerprint. Nothing was added; "
                           "an administrator must check the evidence store (docs/steps/15-2-evidence.md).")
        return key, created

    @staticmethod
    def _copy_exclusive(source: Path, final: Path) -> bool:
        try:
            with source.open("rb") as src, final.open("xb") as out:
                shutil.copyfileobj(src, out, CHUNK)
            return True
        except FileExistsError:
            return False

    def chunks(self, key: str) -> Iterator[bytes]:
        with self._path(key).open("rb") as f:
            while block := f.read(CHUNK):
                yield block

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def hash(self, key: str) -> str | None:
        """The SHA-256 of the stored bytes as they are now; None if the file is missing."""
        path = self._path(key)
        if not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as f:
            while block := f.read(CHUNK):
                digest.update(block)
        return digest.hexdigest()


@lru_cache
def _default_store() -> LocalEvidenceStore:
    return LocalEvidenceStore(get_settings().evidence_root)


def get_evidence_store() -> EvidenceStore:
    """FastAPI dependency (tests replace it with a store in a temporary folder)."""
    return _default_store()
