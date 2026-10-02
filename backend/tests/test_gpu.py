"""Opt-in: real faster-whisper large-v3 on team-recorded clips.  pytest -m gpu

Clips (not in git; real speech only, no synthesized audio):
    backend/tests/fixtures/audio/hi_30s.wav
    backend/tests/fixtures/audio/hinglish_30s.wav
Any format ffmpeg reads is fine; it is converted to 16 kHz mono first.
"""

import pytest

from backend.app.config import load_config
from backend.app.ingestion.audio import extract_audio, load_wav
from backend.app.schemas.project import Language
from backend.app.transcription.asr import FasterWhisperBackend, raw_to_transcript
from backend.tests.helpers import FIX

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def backend():
    b = FasterWhisperBackend(load_config("asr"), "auto")
    if b.device != "cuda":
        pytest.skip("no CUDA device visible to CTranslate2")
    return b


@pytest.mark.parametrize("lang", ["hi", "hinglish"])
def test_real_clip(backend, lang, tmp_path):
    clip = FIX / "audio" / f"{lang}_30s.wav"
    if not clip.exists():
        pytest.skip(f"record {clip.relative_to(FIX.parent.parent.parent)} first")
    wav = tmp_path / "a.wav"
    extract_audio(clip, wav)
    audio = load_wav(wav)
    language = load_config("asr")["language_map"][lang]
    raw1 = backend.transcribe(audio, language)
    raw2 = backend.transcribe(audio, language)
    assert raw1 == raw2, "ASR must be deterministic"
    t = raw_to_transcript(
        raw1,
        "p",
        Language(lang),
        len(audio) / 16000,
        backend.model_id(),
        "h",
        load_config("segmentation")["sentences"],
    )
    assert len(t.words) > 20
    starts = [w.start for w in t.words]
    assert starts == sorted(starts)
    print(
        f"\n[{lang}] detected={t.language_detected} p={t.language_prob:.2f} "
        f"conf={t.mean_confidence}\n{' '.join(w.text for w in t.words)[:400]}"
    )
