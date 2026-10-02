import numpy as np

from backend.app.config import load_config
from backend.app.schemas.project import Language
from backend.app.transcription.asr import raw_to_transcript, transcribe_cached
from backend.tests.helpers import FixtureAsr


def test_raw_to_transcript_maps_and_cleans():
    raw = {
        "language": "hi",
        "language_probability": 0.8,
        "segments": [
            {
                "words": [
                    {"word": " Namaste", "start": 0.5, "end": 0.9, "probability": 0.9},
                    {"word": " ", "start": 0.9, "end": 0.95, "probability": 0.1},
                    {"word": " doston.", "start": 0.85, "end": 0.84, "probability": 0.7},
                ]
            }
        ],
    }
    t = raw_to_transcript(
        raw, "p", Language.HINGLISH, 70.0, "m", "h", load_config("segmentation")["sentences"]
    )
    assert [w.text for w in t.words] == ["Namaste", "doston."]
    assert t.words[1].start >= t.words[0].start and t.words[1].end >= t.words[1].start
    assert t.mean_confidence == 0.8
    assert (t.asr_model, t.asr_config_hash, t.language_detected) == ("m", "h", "hi")
    assert t.duration_s == 70.0 and t.sentences[0].text == "Namaste doston."


def test_cache_hit_skips_model_and_is_encrypted(tmp_path, key):
    backend = FixtureAsr("en")
    audio = np.zeros(16000, dtype=np.float32)
    raw1, h1, hit1 = transcribe_cached(backend, audio, "sha-a", "en", tmp_path, key)
    raw2, h2, hit2 = transcribe_cached(backend, audio, "sha-a", "en", tmp_path, key)
    assert (hit1, hit2) == (False, True) and backend.calls == 1
    assert raw1 == raw2 and h1 == h2
    files = list((tmp_path / "asr").glob("*.enc"))
    assert len(files) == 1 and b"agent" not in files[0].read_bytes()
    # different language option -> different config hash -> cache miss
    _, h3, hit3 = transcribe_cached(backend, audio, "sha-a", None, tmp_path, key)
    assert not hit3 and h3 != h1 and backend.calls == 2
