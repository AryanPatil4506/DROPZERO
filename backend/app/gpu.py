"""Make the pip-installed CUDA libraries (nvidia-cublas-cu12, nvidia-cudnn-cu12) loadable by
CTranslate2 without LD_LIBRARY_PATH / PATH edits. Works on Windows and Linux."""

import contextlib
import ctypes
import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path


def _nvidia_lib_dirs() -> list[Path]:
    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        return []
    sub = "bin" if sys.platform == "win32" else "lib"
    dirs: list[Path] = []
    for root in spec.submodule_search_locations:
        for pkg in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            d = Path(root) / pkg / sub
            if d.is_dir():
                dirs.append(d)
    return dirs


@lru_cache
def ensure_cuda_libs() -> list[str]:
    """Idempotent. Returns the directories that were registered."""
    dirs = _nvidia_lib_dirs()
    if sys.platform == "win32":
        for d in dirs:
            os.add_dll_directory(str(d))
        # CTranslate2 loads cuDNN lazily via LoadLibrary, which also searches PATH.
        os.environ["PATH"] = os.pathsep.join([*map(str, dirs), os.environ.get("PATH", "")])
    else:
        # Preload with RTLD_GLOBAL so later dlopen() calls by name resolve.
        for d in dirs:
            for so in sorted(d.glob("lib*.so*")):
                with contextlib.suppress(OSError):
                    ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
    return [str(d) for d in dirs]


def cuda_device_count() -> int:
    ensure_cuda_libs()
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def resolve_device(pref: str) -> str:
    if pref == "auto":
        return "cuda" if cuda_device_count() > 0 else "cpu"
    return pref
