"""Download every model DROPZERO uses, once, into the local Hugging Face cache (~9 GB).
After this the app runs fully offline (start the backend with HF_HUB_OFFLINE=1).

    python scripts/download_models.py

Model names come from config/*.yaml, so this always matches what the app loads.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import load_config  # noqa: E402


def main() -> None:
    whisper = load_config("asr")["model"]
    labse = load_config("text_features")["embedding"]["model"]
    vis = load_config("av_features").get("content", {})
    clip_models = [m for m in (vis.get("image_model"), vis.get("text_model")) if m]
    llm = load_config("llm")["model"]

    print(f"1/4 Whisper {whisper} (speech to text, ~3 GB)", flush=True)
    from faster_whisper.utils import download_model

    download_model(whisper)

    print(f"2/4 {labse} (sentence meaning, ~1.8 GB)", flush=True)
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(labse)

    for m in clip_models:
        print(f"3/4 {m} (on-screen content)", flush=True)
        SentenceTransformer(m)

    print(f"4/4 {llm} (explanations and rewrites, ~3.4 GB)", flush=True)
    from huggingface_hub import snapshot_download

    snapshot_download(llm, allow_patterns=["*.json", "*.safetensors", "*.txt", "tokenizer*"])
    print("All models downloaded. The app can now run offline.")


if __name__ == "__main__":
    main()
