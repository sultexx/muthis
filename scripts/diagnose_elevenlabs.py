# scripts/diagnose_elevenlabs.py
"""
Diagnostic ONLY — find out EXACTLY why ElevenLabs fails. Run it yourself with
your real .env ELEVENLABS_API_KEY.

It does NOT touch the live TTS pipeline, the cascade, or tts.py — it only REUSES
tts.py's connection constants (read-only import) so there is no drift, and it
reports in Arabic. Two cheap stages:

  1) REST  GET /v1/user/subscription  → auth + quota WITHOUT spending characters
     (the definitive 401 / quota answer).
  2) WebSocket connect + a tiny "مرحبا" synth → reachability + a REAL
     time-to-first-audio-byte latency baseline to compare against Gemini, and a
     faithful reproduction of the live stall symptom.

NEVER prints the API key (only its length, as proof it loaded). NEVER raises
uncaught — every failure mode is caught and explained in Arabic.

    .venv\\Scripts\\python.exe scripts\\diagnose_elevenlabs.py
"""

import asyncio
import base64
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402

# Reuse the EXACT live connection details (read-only) — no duplication, no drift.
from muthis.tts import (  # noqa: E402
    DEFAULT_MODEL_ID, DEFAULT_OUTPUT_FORMAT, DEFAULT_VOICE_ID,
    DEFAULT_VOICE_SETTINGS, ELEVENLABS_WS_BASE,
    WS_CONNECT_TIMEOUT_SEC, WS_TOTAL_TIMEOUT_SEC,
)

REST_BASE = "https://api.elevenlabs.io/v1"
REST_TIMEOUT_SEC = 10.0


# ───────────────────────────── Helpers ─────────────────────────────


def _safe_message(resp) -> str:
    """A short error message from an ElevenLabs response — the key is never in
    the body, so this leaks nothing."""
    try:
        body = resp.json()
    except Exception:
        return (resp.text or "")[:200]
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return (detail.get("message") or detail.get("status")
                or json.dumps(detail, ensure_ascii=False)[:200])
    if isinstance(detail, str):
        return detail[:200]
    return json.dumps(body, ensure_ascii=False)[:200]


# ─────────────────────── Stage 1: REST auth + quota ───────────────────────


def check_auth_and_quota(key: str) -> str:
    """Cheap, definitive auth+quota check. Returns a verdict token."""
    try:
        import httpx
    except ImportError:
        print("⚠️  المرحلة 1: مكتبة httpx غير مثبّتة — تخطّي فحص REST.")
        return "no_httpx"

    url = f"{REST_BASE}/user/subscription"
    try:
        resp = httpx.get(url, headers={"xi-api-key": key}, timeout=REST_TIMEOUT_SEC)
    except httpx.TimeoutException:
        print("⏱️  المرحلة 1 (REST): انتهت المهلة — مشكلة شبكة أو الخادم بطيء.")
        return "timeout"
    except httpx.HTTPError as e:
        print(f"🌐 المرحلة 1 (REST): فشل اتصال الشبكة — {type(e).__name__}.")
        return "network"

    status = resp.status_code
    if status == 401:
        print("🔑 المرحلة 1 (REST): HTTP 401 — المفتاح غير صالح أو منتهي.")
        return "invalid_key"
    if status == 429:
        print("🚫 المرحلة 1 (REST): HTTP 429 — تجاوزت الحصة المجانية / لا يوجد رصيد.")
        return "quota"
    if status != 200:
        print(f"❓ المرحلة 1 (REST): HTTP {status} — {_safe_message(resp)}")
        return "other"

    # 200 — read the actual quota numbers.
    try:
        data = resp.json()
    except Exception:
        print("✅ المرحلة 1 (REST): HTTP 200، لكن تعذّر قراءة JSON الاشتراك.")
        return "ok"
    used, limit = data.get("character_count"), data.get("character_limit")
    tier, sub_status = data.get("tier"), data.get("status")
    if isinstance(used, int) and isinstance(limit, int):
        remaining = limit - used
        print(f"📊 الاشتراك: tier={tier}, status={sub_status}, "
              f"مستهلك={used}/{limit} حرف، متبقٍّ={remaining}.")
        if remaining <= 0:
            print("🚫 المرحلة 1: الرصيد منتهٍ — تجاوزت الحصة المجانية / لا يوجد رصيد.")
            return "quota"
        print("✅ المرحلة 1: الاتصال ناجح، الرصيد متاح — جاهز للـ WebSocket.")
        return "ok"
    print(f"✅ المرحلة 1: HTTP 200 (tier={tier}, status={sub_status}) — مفتاح صالح.")
    return "ok"


# ──────────────── Stage 2: WebSocket time-to-first-audio-byte ────────────────


async def measure_ws_latency(key: str) -> None:
    """Mirror tts.py's exact WS flow (key in the BOS message) and time the first
    audio byte — the latency baseline + a faithful repro of the live behaviour."""
    try:
        import websockets
    except ImportError:
        print("⚠️  المرحلة 2 (WebSocket): مكتبة websockets غير مثبّتة.")
        return

    voice_id = os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
    model_id = os.getenv("ELEVENLABS_MODEL_ID") or DEFAULT_MODEL_ID
    uri = (f"{ELEVENLABS_WS_BASE}/{voice_id}/stream-input"
           f"?model_id={model_id}&output_format={DEFAULT_OUTPUT_FORMAT}")

    print(f"🔌 المرحلة 2 (WebSocket): اتصال (voice={voice_id}, model={model_id})...")
    t_start = time.perf_counter()
    try:
        async with asyncio.timeout(WS_TOTAL_TIMEOUT_SEC):
            async with websockets.connect(
                uri, open_timeout=WS_CONNECT_TIMEOUT_SEC,
            ) as ws:
                print(f"   ✅ تم الاتصال خلال {(time.perf_counter() - t_start) * 1000:.0f}ms.")

                await ws.send(json.dumps({
                    "text": " ",
                    "voice_settings": DEFAULT_VOICE_SETTINGS,
                    "xi_api_key": key,
                }))
                t_send = time.perf_counter()
                await ws.send(json.dumps({"text": "مرحبا ", "try_trigger_generation": True}))
                await ws.send(json.dumps({"text": ""}))

                first_audio_at = None
                total_bytes = 0
                while True:
                    try:
                        msg = await ws.recv()
                    except Exception:
                        break  # ConnectionClosed or similar — end of stream
                    try:
                        data = json.loads(msg)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if data.get("error"):
                        print(f"   ❌ خطأ من ElevenLabs أثناء البث: {data['error']} "
                              f"(غالباً حصة/مفتاح — راجع المرحلة 1).")
                        return
                    audio_b64 = data.get("audio")
                    if audio_b64:
                        if first_audio_at is None:
                            first_audio_at = time.perf_counter()
                            print(f"   🎧 أول بايت صوتي بعد "
                                  f"{(first_audio_at - t_send) * 1000:.0f}ms من إرسال النص "
                                  f"({(first_audio_at - t_start) * 1000:.0f}ms من بدء الاتصال).")
                        total_bytes += len(base64.b64decode(audio_b64))
                    if data.get("isFinal"):
                        break

                if first_audio_at is None:
                    print("   ⚠️  انتهى البث دون أي صوت — غالباً مشكلة حصة/مفتاح (راجع المرحلة 1).")
                else:
                    print(f"   ✅ إجمالي الصوت: {total_bytes} bytes — المسار الحي يعمل تقنياً.")
    except asyncio.TimeoutError:
        print(f"   ⏱️  المرحلة 2: تجاوزت المهلة الكلية ({WS_TOTAL_TIMEOUT_SEC:.0f}s) — "
              f"شبكة بطيئة أو الخادم/الحصة تُعلّق الاتصال (هذا هو عَرَض التعليق الحي).")
    except Exception as e:
        code = getattr(e, "status_code", None)
        if code is None:
            code = getattr(getattr(e, "response", None), "status_code", None)
        if code == 401:
            print("   🔑 المرحلة 2: رفض الخادم الاتصال (401) — المفتاح غير صالح أو منتهي.")
        elif code == 429:
            print("   🚫 المرحلة 2: رفض الخادم الاتصال (429) — تجاوزت الحصة / لا رصيد.")
        elif code is not None:
            print(f"   ❓ المرحلة 2: رفض الخادم الاتصال (HTTP {code}).")
        else:
            print(f"   ❌ المرحلة 2: فشل الـ WebSocket — {type(e).__name__}: {e}")


# ───────────────────────────── Orchestration ─────────────────────────────


async def main() -> None:
    load_dotenv()  # standalone script: load .env ourselves (never committed)
    key = os.getenv("ELEVENLABS_API_KEY")

    print("=" * 64)
    print("تشخيص ElevenLabs — تشخيص فقط، لا يمسّ المسار الحي (tts.py).")
    print("=" * 64)
    if not key:
        print("🔑 لا يوجد ELEVENLABS_API_KEY في .env — لا يمكن التشخيص.")
        return
    print(f"🔑 المفتاح مُحمَّل من .env (طول={len(key)}؛ لن يُطبع المفتاح نفسه).\n")

    print("── المرحلة 1: المصادقة والحصة (REST، بلا استهلاك أحرف) ──")
    verdict = check_auth_and_quota(key)

    if verdict == "invalid_key":
        print("\n⛔ المفتاح غير صالح — تخطّي اختبار الـ WebSocket (لا فائدة).")
        return

    print("\n── المرحلة 2: زمن أول بايت صوتي عبر WebSocket (أساس المقارنة) ──")
    await measure_ws_latency(key)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic on the Windows console
    except Exception:
        pass
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nأُلغي.")
    except Exception as e:  # top-level safety net — never raise uncaught
        print(f"\n❌ خطأ غير متوقّع في التشخيص: {type(e).__name__}: {e}")
