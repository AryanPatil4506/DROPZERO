import pytest

from backend.app.ingestion.probe import parse_ffprobe
from backend.app.ingestion.validate import (
    ValidationError,
    check_video_header,
    decode_script,
    duration_warnings,
)

MP4_HEAD = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"


def test_video_header_accepts_mp4_and_mov():
    check_video_header(MP4_HEAD, "a.mp4")
    check_video_header(b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00", "a.MOV")
    check_video_header(b"\x00\x00\x00\x08wide\x00\x00\x00\x00", "old.mov")


@pytest.mark.parametrize(
    "head,name",
    [
        (b"just some text pretending", "fake.mp4"),  # spoofed extension
        (MP4_HEAD, "clip.avi"),  # wrong extension
        (b"\x00\x00", "short.mp4"),
    ],
)
def test_video_header_rejects(head, name):
    with pytest.raises(ValidationError):
        check_video_header(head, name)


def test_decode_script():
    assert decode_script("﻿नमस्ते।".encode(), "s.txt") == "नमस्ते।"
    assert decode_script(b"# Title\nhello", "s.MD").startswith("# Title")
    for data, name in [
        (b"hello", "s.pdf"),
        (b"\x00\x01binary", "s.txt"),
        (b"\xff\xfe\xfa", "s.txt"),
        (b"   \n ", "s.txt"),
    ]:
        with pytest.raises(ValidationError):
            decode_script(data, name)


def test_duration_bounds():
    with pytest.raises(ValidationError):
        duration_warnings(59.9)
    with pytest.raises(ValidationError):
        duration_warnings(1200.1)
    assert duration_warnings(300) == []
    assert duration_warnings(900) == []
    assert len(duration_warnings(120)) == 1
    assert len(duration_warnings(1000)) == 1


def test_parse_ffprobe():
    info = parse_ffprobe(
        {
            "format": {"duration": "412.5", "format_name": "mov,mp4"},
            "streams": [
                {
                    "codec_type": "video",
                    "avg_frame_rate": "30000/1001",
                    "width": 1920,
                    "height": 1080,
                },
                {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
            ],
        }
    )
    assert info.duration_s == 412.5 and info.has_audio and info.has_video
    assert info.fps == 29.97 and info.audio_sample_rate == 48000
    silent = parse_ffprobe({"format": {"duration": "70"}, "streams": [{"codec_type": "video"}]})
    assert not silent.has_audio
