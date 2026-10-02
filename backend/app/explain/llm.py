"""LLM explanations for flags (CLAUDE.md §10): the LLM narrates measured evidence, never invents it.

Input: a structured evidence object (flag category, time range, feature values with labels) plus a
short transcript excerpt. Output: strict JSON {reason, why_viewers_leave, fix, rewrite}.
Every number / timestamp in the output must appear in the evidence; otherwise retry once, then fall
back to the deterministic template. The response says which source was used.
"""

import json
import re
import threading
from typing import Any

from pydantic import BaseModel

from backend.app.detection.flags import mmss
from backend.app.schemas.flags import Edit, Flag
from backend.app.schemas.transcript import Transcript

LANG_NAMES = {
    "en": "English",
    "hi": "Hindi (Hinglish is fine if the speaker mixes English)",
    "hinglish": "Hinglish (Roman-script Hindi mixed with English)",
}


class Explanation(BaseModel):
    flag_id: str
    source: str  # "llm" | "template"
    model: str | None
    reason: str
    why_viewers_leave: str
    fix: str
    rewrite: str | None = None
    rejected: list[str] = []  # numbers the LLM produced that were not in the evidence


def evidence_object(flag: Flag, edits: list[Edit], t: Transcript, cfg: dict) -> dict[str, Any]:
    words = [w.text for w in t.words if flag.start <= w.start < flag.end]
    excerpt = " ".join(words)[: cfg["excerpt_chars"]]
    return {
        "flag": {
            "category": flag.category,
            "severity": flag.severity,
            "source": flag.source,
            "start": mmss(flag.start),
            "end": mmss(flag.end),
            "title": flag.title,
        },
        "evidence": [
            {
                "label": e.label,
                "value": e.value,
                "unit": e.unit,
                **(
                    {"matches": f"{mmss(e.ref_start)}–{mmss(e.ref_end)}"}
                    if e.ref_start is not None and e.ref_end is not None
                    else {}
                ),
            }
            for e in flag.evidence
        ],
        "suggested_edits": [
            {"action": e.action, "start": mmss(e.start), "end": mmss(e.end), "reason": e.reason}
            for e in edits
            if e.id in flag.edit_ids
        ],
        "transcript_excerpt": excerpt,
    }


_NUM = re.compile(r"\d+(?::\d{2})?(?:\.\d+)?%?")


def allowed_numbers(ev: dict[str, Any]) -> set[str]:
    """Every number string that may legitimately appear: from evidence, edits, times, excerpt."""
    blob = json.dumps(ev, ensure_ascii=False)
    out = set(_NUM.findall(blob))
    for e in ev["evidence"]:
        v = e["value"]
        if isinstance(v, float | int):
            for d in (0, 1, 2):
                out.add(f"{v:.{d}f}")
            if 0 <= v <= 1:  # ratios may be phrased as percentages
                out.update({f"{100 * v:.0f}%", f"{100 * v:.0f}", f"{100 * v:.1f}%"})
    return {x.rstrip("%") for x in out} | out


def check_numbers(text: str, allowed: set[str]) -> list[str]:
    bad = []
    for n in _NUM.findall(text):
        core = n.rstrip("%")
        if n in allowed or core in allowed or core in {"0", "1", "2", "3"}:
            continue  # small counting words ("two things") are not measurements
        bad.append(n)
    return bad


def template(flag: Flag, edits: list[Edit]) -> Explanation:
    fix = "; ".join(e.reason for e in edits if e.id in flag.edit_ids) or "Review this section."
    return Explanation(
        flag_id=flag.id,
        source="template",
        model=None,
        reason=flag.title,
        why_viewers_leave=flag.explanation,
        fix=fix,
    )


SYSTEM = (
    "You are a video editor helping a creator before publishing. You explain why viewers may "
    "leave at a flagged moment. Rules: use ONLY the numbers and timestamps that appear in the "
    "evidence JSON; never invent statistics, percentages or times; do not promise outcomes; say "
    "'may' not 'will'. Reply with ONLY a JSON object with keys: reason (one sentence), "
    "why_viewers_leave (two sentences, plain creator language, cite the evidence), fix (one "
    "concrete instruction with the timestamps given), rewrite (for slow_hook or payoff_delay: "
    "one or two opening lines the creator could say instead, written in {lang}; otherwise null)."
)


class LocalLLM:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._tok = None
        self._model = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.cfg["model"]

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self._tok = AutoTokenizer.from_pretrained(self.cfg["model"])
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = AutoModelForCausalLM.from_pretrained(
                self.cfg["model"], dtype=torch.float16 if device == "cuda" else torch.float32
            ).to(device)
            self._model.eval()
        return self._tok, self._model

    def chat(self, system: str, user: str) -> str:
        import torch

        with self._lock:
            tok, model = self._load()
            msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            prompt = tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            ids = tok(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                out = model.generate(
                    **ids,
                    max_new_tokens=self.cfg["max_new_tokens"],
                    do_sample=self.cfg["do_sample"],
                )
            return tok.decode(out[0][ids["input_ids"].shape[1] :], skip_special_tokens=True)


def _parse(text: str) -> dict | None:
    """First JSON object in the reply; list values (models often return sentence lists) are
    joined into one string."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    for k, v in list(d.items()):
        if isinstance(v, list):
            d[k] = " ".join(str(x) for x in v)
    ok = all(
        isinstance(d.get(k), str) and d[k].strip() for k in ("reason", "why_viewers_leave", "fix")
    )
    return d if ok else None


def explain_flag(
    llm: LocalLLM, flag: Flag, edits: list[Edit], t: Transcript, language: str, cfg: dict
) -> Explanation:
    ev = evidence_object(flag, edits, t, cfg)
    allowed = allowed_numbers(ev)
    system = SYSTEM.replace("{lang}", LANG_NAMES.get(language, "English"))
    user = "Evidence JSON:\n" + json.dumps(ev, ensure_ascii=False, indent=1)
    rejected: list[str] = []
    for attempt in range(cfg["retries"] + 1):
        if attempt:
            user += (
                "\n\nYour previous answer used numbers that are not in the evidence ("
                + ", ".join(rejected)
                + "). Use only numbers from the evidence."
            )
        d = _parse(llm.chat(system, user))
        if d is None:
            rejected = ["(invalid JSON)"]
            continue
        rewrite = d.get("rewrite") if isinstance(d.get("rewrite"), str) else None
        # rewrites are creative text: they may not introduce numbers either
        text = " ".join([d["reason"], d["why_viewers_leave"], d["fix"], rewrite or ""])
        rejected = check_numbers(text, allowed)
        if not rejected:
            return Explanation(
                flag_id=flag.id,
                source="llm",
                model=llm.name,
                reason=d["reason"],
                why_viewers_leave=d["why_viewers_leave"],
                fix=d["fix"],
                rewrite=rewrite,
            )
    out = template(flag, edits)
    out.rejected = rejected
    return out
