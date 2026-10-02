"""Encryption at rest for creator media and derived text.

File format (chunked AES-256-GCM, so large videos never sit fully in memory and byte-range
playback stays possible later):

    header  = b"DZE1" | chunk_size (u32 BE) | nonce_prefix (8 random bytes)
    chunk_i = AESGCM(key).encrypt(nonce_prefix | i (u32 BE), plaintext_i, aad=header | i | last)

`last` (1 byte) is bound into the AAD, so truncating or reordering chunks fails decryption.
"""

import base64
import hashlib
import os
import shutil
import struct
import time
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"DZE1"
CHUNK = 1 << 20
TAG = 16
HEADER_LEN = 4 + 4 + 8


class MediaKeyMissing(RuntimeError):
    pass


def load_key(b64: str) -> bytes:
    if not b64:
        raise MediaKeyMissing(
            "DROPZERO_MEDIA_KEY is not set. Run `python scripts/gen_key.py` and put it in .env."
        )
    key = base64.b64decode(b64)
    if len(key) != 32:
        raise MediaKeyMissing("DROPZERO_MEDIA_KEY must be 32 bytes, base64-encoded.")
    return key


def _aad(header: bytes, i: int, last: bool) -> bytes:
    return header + struct.pack(">I", i) + (b"\x01" if last else b"\x00")


def _read_full(f: BinaryIO, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        b = f.read(n - len(buf))
        if not b:
            break
        buf += b
    return bytes(buf)


def encrypt_stream(key: bytes, src: BinaryIO, dst: BinaryIO, chunk: int = CHUNK) -> tuple[str, int]:
    """Encrypt src into dst. Returns (sha256 of plaintext, plaintext size)."""
    aes = AESGCM(key)
    header = MAGIC + struct.pack(">I", chunk) + os.urandom(8)
    dst.write(header)
    sha = hashlib.sha256()
    size = 0
    i = 0
    cur = _read_full(src, chunk)
    while True:
        nxt = _read_full(src, chunk) if len(cur) == chunk else b""
        last = not nxt
        sha.update(cur)
        size += len(cur)
        nonce = header[8:16] + struct.pack(">I", i)
        dst.write(aes.encrypt(nonce, cur, _aad(header, i, last)))
        if last:
            break
        cur, i = nxt, i + 1
    return sha.hexdigest(), size


def decrypt_chunks(key: bytes, src: BinaryIO) -> Iterator[bytes]:
    aes = AESGCM(key)
    header = _read_full(src, HEADER_LEN)
    if len(header) != HEADER_LEN or header[:4] != MAGIC:
        raise ValueError("not a DROPZERO encrypted file")
    chunk = struct.unpack(">I", header[4:8])[0]
    i = 0
    cur = _read_full(src, chunk + TAG)
    while True:
        nxt = _read_full(src, chunk + TAG) if len(cur) == chunk + TAG else b""
        last = not nxt
        nonce = header[8:16] + struct.pack(">I", i)
        yield aes.decrypt(nonce, cur, _aad(header, i, last))
        if last:
            return
        cur, i = nxt, i + 1


def encrypt_bytes(key: bytes, data: bytes) -> bytes:
    import io

    out = io.BytesIO()
    encrypt_stream(key, io.BytesIO(data), out)
    return out.getvalue()


def decrypt_bytes(key: bytes, blob: bytes) -> bytes:
    import io

    return b"".join(decrypt_chunks(key, io.BytesIO(blob)))


class MediaStore:
    """media/<project_id>/<name>.enc — the only place creator media is kept between jobs."""

    def __init__(self, root: Path, key: bytes):
        self.root = root
        self.key = key

    def path(self, project_id: str, name: str) -> Path:
        return self.root / project_id / f"{name}.enc"

    def put_file(self, project_id: str, name: str, src_path: Path) -> tuple[str, int]:
        dest = self.path(project_id, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".enc.tmp")
        with src_path.open("rb") as s, tmp.open("wb") as d:
            digest = encrypt_stream(self.key, s, d)
        os.replace(tmp, dest)
        return digest

    def put_bytes(self, project_id: str, name: str, data: bytes) -> None:
        dest = self.path(project_id, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(encrypt_bytes(self.key, data))

    def get_bytes(self, project_id: str, name: str) -> bytes:
        return decrypt_bytes(self.key, self.path(project_id, name).read_bytes())

    def decrypt_to(self, project_id: str, name: str, dest: Path) -> None:
        with self.path(project_id, name).open("rb") as s, dest.open("wb") as d:
            for block in decrypt_chunks(self.key, s):
                d.write(block)

    def _layout(self, project_id: str, name: str) -> tuple[Path, bytes, int, int, int]:
        """(path, header, chunk size, chunk count, plaintext size) without decrypting anything."""
        path = self.path(project_id, name)
        with path.open("rb") as f:
            header = _read_full(f, HEADER_LEN)
        if len(header) != HEADER_LEN or header[:4] != MAGIC:
            raise ValueError("not a DROPZERO encrypted file")
        chunk = struct.unpack(">I", header[4:8])[0]
        body = path.stat().st_size - HEADER_LEN
        n = max(1, -(-body // (chunk + TAG)))
        size = body - n * TAG
        return path, header, chunk, n, size

    def plaintext_size(self, project_id: str, name: str) -> int:
        return self._layout(project_id, name)[4]

    def iter_range(self, project_id: str, name: str, start: int, end: int) -> Iterator[bytes]:
        """Yield plaintext bytes [start, end] (inclusive), decrypting only the chunks holding them.

        Each chunk is still authenticated (its index and last-chunk flag are in the AAD), so a
        tampered or truncated file fails here exactly as in a full decrypt.
        """
        path, header, chunk, n, size = self._layout(project_id, name)
        if not 0 <= start <= end < size:
            raise ValueError("range outside the file")
        aes = AESGCM(self.key)
        with path.open("rb") as f:
            for i in range(start // chunk, end // chunk + 1):
                f.seek(HEADER_LEN + i * (chunk + TAG))
                blob = _read_full(f, chunk + TAG)
                nonce = header[8:16] + struct.pack(">I", i)
                plain = aes.decrypt(nonce, blob, _aad(header, i, i == n - 1))
                lo = max(start - i * chunk, 0)
                hi = min(end - i * chunk, len(plain) - 1)
                yield plain[lo : hi + 1]

    def exists(self, project_id: str, name: str) -> bool:
        return self.path(project_id, name).exists()

    def delete_project(self, project_id: str) -> None:
        shutil.rmtree(self.root / project_id, ignore_errors=True)

    def purge_older_than(self, hours: float) -> list[str]:
        """Delete encrypted media older than `hours`. Returns purged project ids."""
        if not self.root.exists():
            return []
        cutoff = time.time() - hours * 3600
        purged = []
        for d in self.root.iterdir():
            if d.is_dir() and all(p.stat().st_mtime < cutoff for p in d.iterdir()):
                shutil.rmtree(d, ignore_errors=True)
                purged.append(d.name)
        return purged
