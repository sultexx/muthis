"""
measure_reasoner.py — DEC-160 measurement (A): the reasoner in APP SHAPE, its time
split at the agent's own `http_client` seam.

    .venv\\Scripts\\python.exe scripts\\measure_reasoner.py plan    projection only, no call
    .venv\\Scripts\\python.exe scripts\\measure_reasoner.py run

APP SHAPE: the real `LunaAgent` with the production persona at the sent size
(`harness.config.production_persona`), the pinned v8 catalogue (the harness
self-test proves a real router hands the model exactly it), the app's own
downscale of a 1920x1080 screen to 1280x720, B0's tool-free phrase, an empty
history, `tool_choice="auto"` and the app's max_output_tokens. The screen is
DEC-98's desktop shot, so this sits beside that probe's 1.90 s. A NEW client per
run: the app warms TLS once at startup (`main.py:182`), and httpx keeps an idle
connection 5 s, so in normal use a turn's first request opens a new one.

THE SPLIT, from httpcore's trace extension on that client (ms from `run()`):
  build    → the request handed to the transport (base64, items, the SDK's JSON)
  connect  TCP + TLS            upload  request headers + body written
  server   body written → response headers
  stream   response headers → the first TextDelta or ToolCall (the app's first_token)
plus the request body's size, the image's bytes and each format's encode time.

VARIANTS, one factor at a time, ten runs each, round-robin so drift spreads:
  effort — every value luna ACCEPTS, starting at today's `high`; a refused value
           fails on its first call at no cost and is recorded as refused · PNG
  format — lossless WebP, JPEG quality 90 · `high`
  control — `high` · PNG, the SAME image every run (luna's cache reaches the image,
           DEC-90). Every other call changes ONE pixel, so its image is fresh while
           the instructions and tools stay cached: a changing screen, the normal case.
Latency and size only, no answer scored or kept. JPEG changes pixels, so adopting
it needs the pointing measurement first; lossless WebP keeps every pixel.
`REASONING_EFFORT` and the media-type sniff are overridden in THIS process only.
"""

from __future__ import annotations

import asyncio
import io
import json
import pathlib
import sys
import time
from dataclasses import dataclass

import latency_common as lc

EFFORTS = ("high", "none", "minimal", "low", "medium", "xhigh", "max")
RUNS = 10
SENT = (1280, 720)
SHOT_INDEX = 2              # DEC-98's corpus, sorted: vscode, fusion, DESKTOP, github
WORST_INPUT_TOKENS = 15_000          # before the first call measures the real figure


@dataclass(frozen=True)
class Variant:
    name: str
    effort: str
    fmt: str
    fresh: bool = True


VARIANTS = ([Variant(f"effort={e}", e, "png") for e in EFFORTS]
            + [Variant("format=webp-lossless", "high", "webp"), Variant("format=jpeg-q90", "high", "jpeg"),
               Variant("control=same-image", "high", "png", fresh=False)])


def encode(image, fmt: str, call: int | None) -> tuple[bytes, float]:
    """The variant's bytes from the app's downscaled frame. `call` changes ONE
    pixel (never the same one twice in a run), so no two calls share an image."""
    if call is not None:
        image = image.copy()
        x, y = call % image.width, call // image.width
        r, g, b = image.getpixel((x, y))
        image.putpixel((x, y), (r ^ 1, g, b))
    buffer = io.BytesIO()
    started = time.perf_counter()
    if fmt == "png":
        image.save(buffer, format="PNG")                   # as vision/downscale.py does
    elif fmt == "webp":
        image.save(buffer, format="WEBP", lossless=True)
    else:
        image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue(), (time.perf_counter() - started) * 1000


def sniff(original):
    def detect(data: bytes) -> str:
        return "image/webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else original(data)
    return detect


def phases(marks: dict, t0: float, first: float | None, end: float) -> dict:
    """The split, in ms from `run()`; None where a mark never came."""
    def at(name):
        return (marks[name] - t0) * 1000 if name in marks else None

    def span(a, b):
        return at(b) - at(a) if at(a) is not None and at(b) is not None else None
    first_ms = (first - t0) * 1000 if first is not None else None
    headers = at("http11.receive_response_headers.complete")
    return {"build": at("request"),
            "connect": span("connection.connect_tcp.started", "connection.start_tls.complete"),
            "upload": span("http11.send_request_headers.started", "http11.send_request_body.complete"),
            "server": span("http11.send_request_body.complete", "http11.receive_response_headers.complete"),
            "stream": first_ms - headers if first_ms is not None and headers is not None else None,
            "first_token": first_ms, "end": (end - t0) * 1000}


async def one(variant: Variant, image_bytes: bytes, setup: dict) -> dict:
    import httpx
    from muthis.cloud import luna_agent
    from muthis.cloud.protocol import TurnComplete, UserInput
    marks, requests = {}, []

    async def trace(name, info):
        marks.setdefault(name, time.perf_counter())

    async def hook(request):
        marks.setdefault("request", time.perf_counter())
        requests.append(int(request.headers.get("content-length") or 0))
        request.extensions["trace"] = trace
    client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0), event_hooks={"request": [hook]})
    agent = luna_agent.LunaAgent(api_key=setup["key"], system_prompt=setup["persona"],
                                 tools=setup["catalogue"], http_client=client)
    luna_agent.REASONING_EFFORT = variant.effort
    row, first, kind, done = {"error": None}, None, None, None
    t0 = time.perf_counter()
    try:
        async for event in agent.run(UserInput(text=setup["phrase"]), image_bytes, [], tool_choice="auto"):
            if isinstance(event, TurnComplete):
                done = event
            elif first is None:
                first, kind = time.perf_counter(), type(event).__name__
    except Exception as exc:  # noqa: BLE001 — a refused effort is a result, not a crash
        row["error"] = {"type": type(exc).__name__, "status": getattr(exc, "status_code", None),
                        "code": getattr(exc, "code", None), "param": getattr(exc, "param", None)}
    finally:
        await client.aclose()
    row.update(phases(marks, t0, first, time.perf_counter()))
    row.update({"first_event": kind, "requests": len(requests), "body_bytes": requests[0] if requests else None})
    if done is not None:
        row.update({"input_tokens": done.input_tokens, "cached_tokens": done.cache_read_input_tokens,
                    "output_tokens": done.output_tokens, "cost_usd": done.cost_usd,
                    "stop_reason": done.stop_reason})
    return row


def worst_call_usd(input_tokens: int) -> float:
    from muthis.cloud.luna_agent import DEFAULT_MAX_TOKENS
    from muthis.cloud.pricing import PRICE_TABLE_USD_PER_MTOK
    price_in, price_out = PRICE_TABLE_USD_PER_MTOK["gpt-5.6-luna"]
    return (input_tokens * price_in + DEFAULT_MAX_TOKENS * price_out) / 1_000_000


def plan() -> dict:
    calls = len(VARIANTS) * RUNS
    worst = worst_call_usd(WORST_INPUT_TOKENS)
    # Expected: B0's logged luna passes averaged $0.00073 (DEC-159 ①); a fresh image
    # adds its ~4,860 uncached tokens (DEC-90) at $0.20/M.
    expected = calls * (0.00073 + 4_860 * 0.20 / 1_000_000)
    return {"variants": [v.name for v in VARIANTS], "runs": RUNS, "calls_at_most": calls,
            "expected_usd": round(expected, 3), "worst_usd": round(calls * worst, 3),
            "share_usd": lc.SHARES["reasoner"][0]}


async def run() -> int:
    from PIL import Image
    from harness.config import V8_SNAPSHOT, production_persona
    from muthis.cloud import luna_agent
    from muthis.vision.downscale import downscale_to_max_width
    from voice_b0 import PLAN
    lc.console()
    shots = sorted((pathlib.Path.home() / "Desktop" / "muthis_grounding" / "shots").glob("*.png"))
    frame = (await downscale_to_max_width(shots[SHOT_INDEX].read_bytes())).sent_bytes
    base = Image.open(io.BytesIO(frame)).convert("RGB")
    assert base.size == SENT, base.size
    setup = {"key": lc.key("OPENAI_API_KEY"), "persona": production_persona(SENT),
             "catalogue": json.loads(V8_SNAPSHOT.read_text(encoding="utf-8")), "phrase": PLAN[0].phrase}
    luna_agent.detect_image_media_type = sniff(luna_agent.detect_image_media_type)
    spend, refused, rows, call = lc.Spend("reasoner"), {}, [], 0
    worst, before, folder = worst_call_usd(WORST_INPUT_TOKENS), lc.log_guard(), lc.results_dir("reasoner")
    print(json.dumps(plan(), indent=1))
    for rep in range(1, RUNS + 1):
        for variant in VARIANTS:
            if variant.effort in refused and variant.name.startswith("effort="):
                continue
            spend.allow(usd=worst)
            data, encode_ms = encode(base, variant.fmt, call if variant.fresh else None)
            call += 1
            row = {"variant": variant.name, "rep": rep, "image_bytes": len(data),
                   "encode_ms": encode_ms, **await one(variant, data, setup)}
            spend.add(usd=row.get("cost_usd") or 0.0)
            if row.get("input_tokens"):
                worst = worst_call_usd(row["input_tokens"])
            if row["error"] and row["error"]["status"] == 400 and rep == 1:
                refused[variant.effort] = row["error"]
            rows.append(row)
            print(f"{variant.name:22} rep {rep:2}: first_token {row['first_token'] or 0:7.0f} ms "
                  f"(build {row['build'] or 0:4.0f} connect {row['connect'] or 0:4.0f} "
                  f"upload {row['upload'] or 0:4.0f} server {row['server'] or 0:5.0f} "
                  f"stream {row['stream'] or 0:5.0f}) {row['error'] or ''}")
    keys = ("first_token", "build", "connect", "upload", "server", "stream", "end", "encode_ms",
            "image_bytes", "body_bytes", "cached_tokens", "input_tokens", "output_tokens")
    summary = {v.name: {k: lc.stats([r.get(k) for r in rows if r["variant"] == v.name and not r["error"]])
                        for k in keys} for v in VARIANTS if not (v.effort in refused and v.name.startswith("effort="))}
    out = lc.write(folder, "reasoner.json", {
        "schema": "latency-reasoner/1", "created_utc": lc.utc_stamp(), "plan": plan(),
        "refused_efforts": refused, "summary": summary, "rows": rows, "spend": spend.as_dict(),
        "durable_log_changes": lc.log_changes(before)})
    print(f"\nspend ${spend.usd:.4f}; refused efforts {sorted(refused)}; record {out}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["plan"]:
        print(json.dumps(plan(), indent=1))
        sys.exit(0)
    sys.exit(asyncio.run(run()) if sys.argv[1:] == ["run"] else print(__doc__) or 2)
