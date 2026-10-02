import base64
import os

import pytest

from backend.app.config import load_config
from backend.app.schemas.project import Language
from backend.app.settings import Settings
from backend.app.transcription.asr import raw_to_transcript
from backend.tests.helpers import load_raw

LANGS = ["en", "hi", "hinglish"]


@pytest.fixture
def seg_cfg():
    return load_config("segmentation")


@pytest.fixture
def key() -> bytes:
    return os.urandom(32)


@pytest.fixture
def settings(tmp_path, key) -> Settings:
    return Settings(
        data_dir=tmp_path / "var",
        media_key=base64.b64encode(key).decode(),
        _env_file=None,
    )


def fixture_transcript(lang: str):
    raw = load_raw(lang)
    return raw_to_transcript(
        raw,
        f"p-{lang}",
        Language(lang),
        raw["duration"],
        "fixture/asr",
        "h",
        load_config("segmentation")["sentences"],
    )


@pytest.fixture(params=LANGS)
def lang(request) -> str:
    return request.param
