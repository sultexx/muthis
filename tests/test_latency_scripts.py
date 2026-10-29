"""
test_latency_scripts.py — DEC-160's standalone latency measurements, proven without
a provider, a socket or a device.

What is pinned: the round's shares fit inside the brief's caps and a call that would
cross its share is refused BEFORE it is made; a transcript leaves nothing behind but
its class (match · near · miss · empty · failed), on either path; the reasoner's
split is computed from httpcore's trace marks; every reasoner call gets an image no
other call sent, lossless WebP keeps every pixel and JPEG does not; WebP is named
for what it is; the number test's table is what it claims (digits, Arabic-Indic
digits, words); and a TTS generation counts what it sends and sends the end of
stream only after the first audio.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET = "كلمة_سرية_في_النص"


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lc = _load("latency_common")
stt = _load("measure_stt")
reasoner = _load("measure_reasoner")
voice = _load("measure_voice_start")
numbers = _load("tts_numbers_ab")


# ─── Spend ────────────────────────────────────────────────────────────────────

def test_the_shares_fit_inside_the_brief_caps():
    assert sum(usd for usd, _ in lc.SHARES.values()) <= 0.50
    assert sum(chars for _, chars in lc.SHARES.values()) <= 15_000


def test_a_call_that_would_cross_its_share_is_refused_before_it_is_made():
    spend = lc.Spend("stt")
    spend.allow(usd=0.04)
    spend.add(usd=0.04)
    with pytest.raises(SystemExit):
        spend.allow(usd=0.02)
    with pytest.raises(SystemExit):
        lc.Spend("voice_start").allow(chars=4_001)


def test_each_projection_fits_its_share():
    assert reasoner.plan()["expected_usd"] <= lc.SHARES["reasoner"][0]
    assert stt.plan()["projected_usd"] <= lc.SHARES["stt"][0]
    assert voice.plan()["projected_chars"] <= lc.SHARES["voice_start"][1]


# ─── Transcription: the class, never the words ────────────────────────────────

def test_a_transcript_is_reduced_to_its_class():
    phrase = "كم يوم في السنة الكبيسة؟"
    assert stt.match("كم يوم في السنة الكبيسه", phrase) == "match"      # ة/ه, punctuation
    assert stt.match("كم يوم في السنة الكبيسي", phrase) == "near"
    assert stt.match("وين زر الحفظ", phrase) == "miss"
    assert stt.match("  ", phrase) == "empty" and stt.match(None, phrase) == "failed"


def test_the_batch_row_keeps_no_text(monkeypatch):
    async def fake(self, wav):
        return SECRET
    monkeypatch.setattr("muthis.stt.STT._scribe_request", fake)
    row = asyncio.run(stt.batch("k", b"wav", "كم يوم"))
    assert row["match"] == "miss" and SECRET not in json.dumps(row, ensure_ascii=False)


class _FakeSocket:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []
        self.close_code = self.close_reason = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def recv(self):
        if not self.replies:
            await asyncio.sleep(3600)
        return self.replies.pop(0)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.replies:
            raise StopAsyncIteration
        return self.replies.pop(0)

    async def send(self, message):
        self.sent.append(json.loads(message))


def test_the_realtime_row_keeps_no_text_and_commits_on_the_last_chunk(monkeypatch):
    import websockets
    sock = _FakeSocket([json.dumps({"message_type": "session_started"}),
                        json.dumps({"message_type": "committed_transcript", "text": SECRET})])
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: sock)
    row = asyncio.run(stt.realtime("k", b"\x00\x00" * 4000, "كم يوم"))
    assert [m["commit"] for m in sock.sent] == [False, False, True], "commit must ride the LAST chunk"
    assert row["error"] is None and row["match"] == "miss"
    assert SECRET not in json.dumps(row, ensure_ascii=False)


# ─── The reasoner's split and its images ──────────────────────────────────────

def test_the_split_comes_from_the_trace_marks():
    marks = {"request": 1.010, "connection.connect_tcp.started": 1.011,
             "connection.start_tls.complete": 1.111, "http11.send_request_headers.started": 1.112,
             "http11.send_request_body.complete": 1.312,
             "http11.receive_response_headers.complete": 2.312}
    p = reasoner.phases(marks, 1.000, 3.000, 3.500)
    assert [round(p[k]) for k in ("build", "connect", "upload", "server", "stream", "first_token", "end")] \
        == [10, 100, 200, 1000, 688, 2000, 2500]
    assert reasoner.phases({}, 1.0, None, 2.0)["stream"] is None


def test_every_call_sends_an_image_no_other_call_sent_and_only_webp_keeps_every_pixel():
    from PIL import Image, ImageChops
    base = Image.new("RGB", (64, 36), (120, 30, 200))
    first, second, same = (reasoner.encode(base, "png", n)[0] for n in (0, 1, None))
    assert len({first, second, same}) == 3
    diff = ImageChops.difference(Image.open(io.BytesIO(first)).convert("RGB"), base)
    raw = diff.tobytes()
    assert sum(raw[i:i + 3] != b"\0\0\0" for i in range(0, len(raw), 3)) == 1, "exactly one pixel changes"
    webp = Image.open(io.BytesIO(reasoner.encode(base, "webp", None)[0])).convert("RGB")
    assert ImageChops.difference(webp, base).getbbox() is None, "lossless WebP lost a pixel"
    noisy = Image.effect_noise((64, 36), 64).convert("RGB")
    jpeg = Image.open(io.BytesIO(reasoner.encode(noisy, "jpeg", None)[0])).convert("RGB")
    assert ImageChops.difference(jpeg, noisy).getbbox() is not None


def test_webp_is_named_for_what_it_is():
    detect = reasoner.sniff(lambda data: "image/png")
    assert detect(b"RIFF\x00\x00\x00\x00WEBPVP8L") == "image/webp" and detect(b"\x89PNG") == "image/png"


# ─── The number test's table ──────────────────────────────────────────────────

def test_the_number_table_is_digits_arabic_indic_and_words():
    assert len(numbers.SENTENCES) == 12
    for digits, words in numbers.SENTENCES:
        indic = numbers.to_indic(digits)
        assert any(c.isdigit() for c in digits) and not any(c in "0123456789" for c in indic)
        assert not any(c.isdigit() for c in words), f"a digit in the words column: {words}"
    assert "٣٫١٣" in numbers.to_indic("هو 3.13.") and numbers.to_indic("85%") == "٨٥٪"
    assert numbers.to_indic("1,250") == "١٬٢٥٠"
    counts = {arm: sum(i["arm"] == arm for i in numbers.items("ABCD")) for arm in "ABCD"}
    assert counts == {"A": 24, "B": 24, "C": 12, "D": 24}
    assert numbers.plan()["projected_chars"] <= numbers.CAP_CHARS


# ─── One TTS generation ───────────────────────────────────────────────────────

def test_a_generation_counts_what_it_sends_and_ends_the_stream_after_the_first_audio(monkeypatch):
    import base64
    import websockets
    audio = base64.b64encode(b"\x00\x00" * 2205).decode()
    sock = _FakeSocket([json.dumps({"audio": audio}), json.dumps({"audio": audio, "isFinal": True})])
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: sock)
    row = asyncio.run(lc.tts_generate("key", "wss://x", "مرحبا"))
    from muthis.tts_diacritics import apply_diacritics
    assert row["chars_sent"] == 1 + len(apply_diacritics("مرحبا") + " ")
    assert [m.get("text") for m in sock.sent] == [" ", apply_diacritics("مرحبا") + " ", ""]
    assert sock.sent[1]["flush"] and sock.sent[1]["try_trigger_generation"]
    assert row["error"] is None and round(row["first_chunk_ms_of_audio"]) == 100
    assert "key" not in json.dumps(row)


def test_results_never_land_inside_the_repository():
    with pytest.raises(SystemExit):
        lc.write(ROOT / "tests", "x.json", {})
