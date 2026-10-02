import io
import os

import pytest
from cryptography.exceptions import InvalidTag

from backend.app.storage.media_store import (
    MediaKeyMissing,
    MediaStore,
    decrypt_chunks,
    encrypt_stream,
    load_key,
)


@pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 48, 100])
def test_roundtrip_chunk_edges(key, size):
    data = os.urandom(size)
    out = io.BytesIO()
    sha, n = encrypt_stream(key, io.BytesIO(data), out, chunk=16)
    assert n == size
    assert b"".join(decrypt_chunks(key, io.BytesIO(out.getvalue()))) == data
    import hashlib

    assert sha == hashlib.sha256(data).hexdigest()


def test_ciphertext_differs_and_tamper_detected(key):
    data = b"unpublished creator video " * 100
    out = io.BytesIO()
    encrypt_stream(key, io.BytesIO(data), out, chunk=64)
    blob = out.getvalue()
    assert data[:40] not in blob
    # dropping the whole final chunk must fail, not silently return a shorter file
    last_chunk_len = len(data) % 64 + 16
    with pytest.raises(InvalidTag):
        b"".join(decrypt_chunks(key, io.BytesIO(blob[:-last_chunk_len])))
    flipped = bytearray(blob)
    flipped[40] ^= 1
    with pytest.raises(InvalidTag):
        b"".join(decrypt_chunks(key, io.BytesIO(bytes(flipped))))
    with pytest.raises(InvalidTag):
        b"".join(decrypt_chunks(os.urandom(32), io.BytesIO(blob)))


def test_store_never_touches_source(tmp_path, key):
    src = tmp_path / "creator.mp4"
    payload = os.urandom(3 << 20)
    src.write_bytes(payload)
    before = src.stat().st_mtime_ns
    store = MediaStore(tmp_path / "media", key)
    store.put_file("p1", "original", src)
    assert src.read_bytes() == payload and src.stat().st_mtime_ns == before
    assert store.path("p1", "original").read_bytes()[:100] != payload[:100]
    out = tmp_path / "dec.mp4"
    store.decrypt_to("p1", "original", out)
    assert out.read_bytes() == payload
    store.delete_project("p1")
    assert not store.path("p1", "original").exists()


def test_key_validation():
    with pytest.raises(MediaKeyMissing):
        load_key("")
    with pytest.raises(MediaKeyMissing):
        load_key("c2hvcnQ=")


@pytest.mark.parametrize("size", [1, 16, 17, 100, 160])
def test_iter_range_decrypts_only_requested_bytes(key, tmp_path, size):
    store = MediaStore(tmp_path / "media", key)
    data = os.urandom(size)
    dest = store.path("p", "original")
    dest.parent.mkdir(parents=True)
    with dest.open("wb") as d:
        encrypt_stream(key, io.BytesIO(data), d, chunk=16)
    assert store.plaintext_size("p", "original") == size
    for start, end in [
        (0, size - 1),
        (0, 0),
        (size - 1, size - 1),
        (size // 3, size - 1),
        (5 % size, min(40, size - 1)),
    ]:
        if start > end:
            continue
        assert b"".join(store.iter_range("p", "original", start, end)) == data[start : end + 1]
    with pytest.raises(ValueError):
        list(store.iter_range("p", "original", 0, size))


def test_iter_range_detects_tampering(key, tmp_path):
    store = MediaStore(tmp_path / "media", key)
    dest = store.path("p", "original")
    dest.parent.mkdir(parents=True)
    with dest.open("wb") as d:
        encrypt_stream(key, io.BytesIO(os.urandom(64)), d, chunk=16)
    blob = bytearray(dest.read_bytes())
    blob[-3] ^= 1  # last chunk
    dest.write_bytes(bytes(blob))
    with pytest.raises(InvalidTag):
        list(store.iter_range("p", "original", 60, 63))
