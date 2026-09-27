"""
capture.py — Sultan's tool for the four fixture screens (ruling ②). NEVER run
by an agent: it photographs the live primary monitor, which is personal data
until a human has looked at it.

  python scripts/harness/capture.py <name>            capture after a countdown
  python scripts/harness/capture.py <name> --review   record the file as reviewed

Capture uses the production `ScreenCapture` (the frame a turn would take), saves
`fixtures/screens/<name>.png`, and prints its sha256 and the size it is SENT at.
It never marks a screen reviewed. `--review` is a separate, deliberate act: it
writes the file's CURRENT sha256 and `reviewed: true` into the manifest, so a
screen changed after review no longer matches and a live run refuses it.

Note: `.gitignore` ignores `*.png`; committing the screens is a separate ruling.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
for entry in (REPO / "scripts", REPO / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from muthis.vision.downscale import downscale_to_max_width  # noqa: E402
from muthis.vision.screen_capture import ScreenCapture  # noqa: E402

SCREENS = pathlib.Path(__file__).resolve().parent / "fixtures" / "screens"
MANIFEST = SCREENS / "MANIFEST.json"


def _entry(name: str) -> tuple[dict, dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if name not in manifest["screens"]:
        raise SystemExit(f"unknown screen {name!r}; one of {sorted(manifest['screens'])}")
    return manifest, manifest["screens"][name]


def capture(name: str, countdown_s: int = 8) -> None:
    manifest, entry = _entry(name)
    print(f"Arrange the screen: {entry['shows']}. NO personal data may be visible.")
    for left in range(countdown_s, 0, -1):
        print(f"  capturing in {left} s", flush=True)
        time.sleep(1)
    png = asyncio.run(ScreenCapture().capture())
    if not png:
        raise SystemExit("capture failed")
    path = SCREENS / entry["file"]
    path.write_bytes(png)
    sent = asyncio.run(downscale_to_max_width(png))
    size = (sent.sent_width, sent.sent_height)
    print(f"saved {path}\n  sha256 {hashlib.sha256(png).hexdigest()}\n  sent at {size}")
    print("Open the image and check it. Then, and only then: --review")
    entry["reviewed"], entry["sha256"] = False, None
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def review(name: str) -> None:
    manifest, entry = _entry(name)
    path = SCREENS / entry["file"]
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    entry["reviewed"] = True
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"{name}: reviewed at sha256 {entry['sha256']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if "--review" in sys.argv[2:]:
        review(sys.argv[1])
    else:
        capture(sys.argv[1])
