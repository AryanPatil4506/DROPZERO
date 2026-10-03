"""Warm the demo: run every slow first-time action once so the live demo is instant.

Needs the backend running. For the golden project (title "I Built an AI Agent in 24 Hours",
file demo_ai_agent.mp4): AI explanation for each key flag, a rewrite for the repetition and
the slow hook, one render of the main edits, and the scripted A/B comparison.

    python scripts/warm_demo.py
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = "http://127.0.0.1:8000/api"


def call(path, body=None, method=None, timeout=900):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        B + path,
        data=data,
        method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def main() -> None:
    try:
        call("/health")
    except (urllib.error.URLError, OSError):
        sys.exit("Backend is not running: start it first (see README / docs/demo-script.md).")
    golden = [p for p in call("/projects") if p.get("source_filename") == "demo_ai_agent.mp4"]
    if not golden:
        sys.exit(
            "No golden project: run scripts/make_demo_video.py, then upload it (or "
            "scripts/precompute.py)."
        )
    pid = golden[0]["id"]
    fl = call(f"/projects/{pid}/flags")
    key = [
        f
        for f in fl["flags"]
        if f["category"] in ("slow_hook", "payoff_delay", "repetition", "low_information")
    ]
    for f in key:
        t0 = time.time()
        e = call(f"/projects/{pid}/flags/{f['id']}/explain", method="POST")
        print(f"explain {f['id']} {f['category']:13s} {e['source']:8s} {time.time() - t0:5.1f}s")
    order = {"repetition": 0, "slow_hook": 1, "payoff_delay": 2}
    for f in sorted([x for x in key if x["category"] in order], key=lambda x: order[x["category"]])[
        :3
    ]:
        t0 = time.time()
        r = call(f"/projects/{pid}/flags/{f['id']}/rewrite", method="POST")
        print(
            f"rewrite {f['id']} {f['category']:13s} {r['source']:8s} {time.time() - t0:5.1f}s "
            f"{r.get('rejected') or ''}"
        )
    cuts = [e["id"] for e in fl["edits"] if e["action"] == "CUT"]
    st = call(f"/projects/{pid}/render", {"edit_ids": cuts})
    while st["status"] in ("queued", "running"):
        time.sleep(2)
        st = call(f"/projects/{pid}/renders/{st['render_id']}")
    print("render", st["status"], st.get("encoder"), st.get("error") or "")
    demo = ROOT / "data" / "private" / "demo"
    ab = call(
        "/ab-test",
        {
            "title": "I Built an AI Agent in 24 Hours",
            "language": "en",
            "script_a": (demo / "ab_original.txt").read_text(encoding="utf-8"),
            "script_b": (demo / "ab_promise_first.txt").read_text(encoding="utf-8"),
            "name_a": "Original intro",
            "name_b": "Promise-first hook",
        },
    )
    print("A/B:", ab["summary"])
    print(f"\nGolden project: http://127.0.0.1:5173/projects/{pid}")


if __name__ == "__main__":
    main()
