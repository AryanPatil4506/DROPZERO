"""MOOCCubeX caption record -> Transcript, so lectures go through the exact same segmentation and
feature code as creator videos. Chinese has no spaces: each character is a word, with times spread
evenly across its caption line; each caption line is a sentence."""

from typing import Any

from backend.app.schemas.project import Language
from backend.app.schemas.transcript import Sentence, TimingSource, Transcript, Word
from backend.app.versions import TRANSCRIPT_SCHEMA_VERSION


def captions_to_transcript(rec: dict[str, Any], duration_s: float) -> Transcript:
    words: list[Word] = []
    sentences: list[Sentence] = []
    lines = sorted(zip(rec["start"], rec["end"], rec["text"], strict=False))
    for start, end, text in lines:
        chars = [c for c in str(text) if not c.isspace()]
        if not chars or end <= start:
            continue
        start = max(start, words[-1].end if words else 0.0)
        end = max(end, start + 0.01)
        step = (end - start) / len(chars)
        w0 = len(words)
        for k, c in enumerate(chars):
            words.append(
                Word(text=c, start=round(start + k * step, 3), end=round(start + (k + 1) * step, 3))
            )
        sentences.append(
            Sentence(
                idx=len(sentences),
                start=words[w0].start,
                end=words[-1].end,
                text="".join(chars),
                word_start=w0,
                word_end=len(words),
                end_reason="punct",
            )
        )
    return Transcript(
        project_id=rec["ccid"],
        language_declared=Language.ZH,
        timing_source=TimingSource.ASR,  # human/platform captions with real timestamps
        duration_s=round(max(duration_s, words[-1].end if words else 0.0), 3),
        words=words,
        sentences=sentences,
        transcript_schema_version=TRANSCRIPT_SCHEMA_VERSION,
    )
