# src/safeguard/audio/asr.py
"""
WhisperASR — Arabic-first speech-to-text wrapper around faster-whisper.

Entry point for the Concierge scenario (§1 Part 1):
  microphone audio → WhisperASR.transcribe(...) → Arabic text → Qwen reasoner.

Design contract (matches the other wrappers):
  - Dependency injection. The Orchestrator loads the faster-whisper model
    (with the CTranslate2 CUDA-build verified by startup_check, §3.3) and
    hands it in. This class NEVER loads or unloads.
  - It does NOT acquire gpu_lock. The orchestrator handler holds it
    (Golden Rule #1).
  - Blocking work runs inside asyncio.to_thread so the event loop is never
    starved while CTranslate2 decodes.
  - NOT thread-safe; serialization is the orchestrator's gpu_lock job.

Arabic-first hardening (§1, §14.4) — Bug fix iteration v2:
  Original behavior had `language="ar"` and `task="transcribe"`, which is
  necessary but NOT sufficient. Whisper large-v3 exhibits well-known
  code-switching: it will transcribe English brand names (YouTube, Netflix,
  WhatsApp, etc.) in Latin script even inside Arabic utterances. Also, if
  an entire utterance happens to be English, it may quietly ignore the
  `language` parameter.

  Layered defenses applied here, in order of effectiveness:

    Defense 1 — `language="ar"` + `task="transcribe"` (strict, never translate).
    Defense 2 — `initial_prompt` priming with an Arabic context sentence,
                so the decoder starts conditioned on Arabic tokens.
    Defense 3 — `condition_on_previous_text=False` to stop an English
                pattern in one segment from carrying into the next.
    Defense 4 — Explicit `is_likely_arabic` flag. If the detected language
                came back as something other than `ar`, we surface that so
                the orchestrator can re-prompt the user instead of acting
                on garbled text. (See `Transcription.is_likely_arabic`.)

  What we explicitly do NOT promise:
    Whisper's code-switching CANNOT be fully suppressed — that's a property
    of the upstream model weights, not a configuration knob. The pragmatic
    surface area for callers is: trust `text` for short Arabic utterances,
    re-prompt when `is_likely_arabic` is False.

Architecture refs:
  §1, §14.4   Arabic-first product → language='ar', initial_prompt='ar'.
  §3.3        CTranslate2 CUDA-build lock — Silent-CPU-Fallback gate is
              startup_check's job. We trust the orchestrator here.
  §5.4        gpu_lock is held by the caller — serialized w.r.t. Qwen /
              OmniParser inferences.
  §14.2       Recovery — .is_empty / .is_confident / .is_likely_arabic
              let the caller decide to ask the user to repeat instead of
              acting on noise or wrong-language audio.
  §17.10      num_beams > 1 forbidden → beam_size=1 (greedy decoding).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Union

import numpy as np

logger = logging.getLogger("whisper_asr")


# ─── Type alias for accepted audio inputs ─────────────────────────────────────

AudioInput = Union[str, Path, np.ndarray, bytes]


# ─── Defaults ─────────────────────────────────────────────────────────────────

# Arabic-first product (§1, §14.4 pitch point: "عربي بالأصل، ليس مترجَماً").
DEFAULT_LANGUAGE = "ar"

# Strictly transcribe — NEVER translate. `translate` would emit English.
# This is a hard constant, NOT user-overridable.
TASK_TRANSCRIBE = "transcribe"

# Greedy decoding — equivalent of num_beams=1 (Golden Rule #10 in spirit).
DEFAULT_BEAM_SIZE = 1

# VAD — strips leading/trailing silence so we don't pay for empty audio.
DEFAULT_VAD_FILTER = True
DEFAULT_VAD_MIN_SILENCE_MS = 500

# Trust threshold for the forced-language detector. Below this, the audio
# probably wasn't Arabic — caller can retry per §14.2 recovery.
MIN_LANGUAGE_CONFIDENCE = 0.5

# Arabic context primer — keeps the decoder conditioned on Arabic tokens
# from the first frame. The text is innocuous Arabic banking vocabulary
# (no PII, no commands) so it won't bias the actual transcription content.
# It exists to nudge the decoder's language head toward Arabic.
DEFAULT_ARABIC_INITIAL_PROMPT = (
    "مرحباً، هذه محادثة باللغة العربية مع مساعد مصرفي. "
    "نتحدث عن الحوالات، الفواتير، والخدمات البنكية."
)


# ─── Result models ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Segment:
    """One contiguous transcribed segment with its time interval (seconds)."""
    text:  str
    start: float
    end:   float


@dataclass(frozen=True)
class Transcription:
    """
    Result of WhisperASR.transcribe().
    `text` is the full concatenated utterance, stripped.
    """
    text:                 str
    language:             str       # what the detector saw (target: 'ar')
    language_probability: float     # confidence in detected language
    duration:             float     # audio length in seconds
    segments:             List[Segment]
    is_confident:         bool      # language_probability >= threshold
    is_likely_arabic:     bool      # detected language == 'ar' AND confident

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


# ─── WhisperASR ───────────────────────────────────────────────────────────────

class WhisperASR:
    """
    Arabic speech-to-text wrapper. Stateless beyond its config; the heavy
    state (model weights, CTranslate2 graph) lives in the injected `model`.
    """

    def __init__(
        self,
        model: Any,
        *,
        default_language: str = DEFAULT_LANGUAGE,
        default_initial_prompt: Optional[str] = DEFAULT_ARABIC_INITIAL_PROMPT,
        default_beam_size: int = DEFAULT_BEAM_SIZE,
        vad_filter: bool = DEFAULT_VAD_FILTER,
        vad_min_silence_ms: int = DEFAULT_VAD_MIN_SILENCE_MS,
    ) -> None:
        if model is None:
            raise ValueError(
                "WhisperASR requires the orchestrator-loaded faster-whisper "
                "model. This class does not load it itself."
            )
        if default_beam_size != 1:
            raise ValueError(
                f"default_beam_size must be 1 (Golden Rule #10). "
                f"Got {default_beam_size}."
            )

        self.model = model
        self.default_language = default_language
        self.default_initial_prompt = default_initial_prompt
        self.default_beam_size = default_beam_size
        self.vad_filter = vad_filter
        self.vad_parameters = {"min_silence_duration_ms": vad_min_silence_ms}

    # ─────────────────────────── Public API ───────────────────────────

    async def transcribe(
        self,
        audio: AudioInput,
        *,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        beam_size: Optional[int] = None,
    ) -> Transcription:
        """
        Transcribe an utterance to Arabic text.

        Args:
            audio: a file path (str/Path), raw bytes, or a numpy array
                   (mono, float32, 16 kHz).
            language: override the default 'ar'. Don't change unless you
                      know what you're doing — code-switching defenses
                      assume Arabic context.
            initial_prompt: optional Arabic priming text. By default we
                            use DEFAULT_ARABIC_INITIAL_PROMPT to bias
                            the decoder's language head toward Arabic.
                            Pass an empty string "" to disable priming.
            beam_size: override greedy decoding. MUST stay 1 per
                       Golden Rule #10.

        Returns:
            Transcription. The caller should check `.is_likely_arabic`
            (not just `.is_confident`) before acting on `text` for
            Arabic-required flows.

        Concurrency:
            Caller MUST be holding orchestrator.gpu_lock — Whisper shares
            the GPU with Qwen and OmniParser (Golden Rule #1).
        """
        effective_language = language or self.default_language
        # `initial_prompt=""` from caller is treated as "disable", whereas
        # `None` means "use default". This lets the caller opt out cleanly.
        if initial_prompt is None:
            effective_prompt = self.default_initial_prompt
        else:
            effective_prompt = initial_prompt or None

        return await asyncio.to_thread(
            self._transcribe_sync,
            audio,
            effective_language,
            effective_prompt,
            beam_size if beam_size is not None else self.default_beam_size,
        )

    # ─────────────────────── Sync core (blocking) ───────────────────────

    def _transcribe_sync(
        self,
        audio: AudioInput,
        language: str,
        initial_prompt: Optional[str],
        beam_size: int,
    ) -> Transcription:
        # Defense in depth — re-validate Golden Rule #10 immediately
        # before the call. A future config edit can't silently break this.
        if beam_size != 1:
            raise ValueError(
                f"beam_size must be 1 (Golden Rule #10). Got {beam_size}."
            )

        # Normalize path-like input — faster-whisper expects str, not Path.
        if isinstance(audio, Path):
            audio = str(audio)

        # ── Defense-in-depth kwargs ────────────────────────────────────
        # task is HARDCODED — no caller can request translation.
        kwargs = {
            "language":                  language,
            "task":                      TASK_TRANSCRIBE,
            "beam_size":                 beam_size,
            "vad_filter":                self.vad_filter,
            "vad_parameters":            self.vad_parameters,
            # Prevent previous-segment English patterns from carrying over.
            "condition_on_previous_text": False,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        segments_iter, info = self.model.transcribe(audio, **kwargs)

        # CRITICAL: materialize the generator HERE (inside the thread).
        # faster-whisper does lazy decoding — iteration is what actually
        # runs CTranslate2.
        segments: List[Segment] = []
        parts:    List[str]     = []
        for s in segments_iter:
            segments.append(Segment(text=s.text, start=s.start, end=s.end))
            parts.append(s.text)

        full_text = "".join(parts).strip()
        is_confident = info.language_probability >= MIN_LANGUAGE_CONFIDENCE
        # Stricter flag — must be Arabic AND confident.
        is_likely_arabic = (info.language == "ar") and is_confident

        if not is_likely_arabic:
            logger.warning(
                "[WhisperASR] non-Arabic or low-confidence: lang=%s prob=%.2f — "
                "consider re-prompting the user (§14.2).",
                info.language, info.language_probability,
            )

        # Privacy (§17.5): log a short preview at most, not the full text.
        preview = (full_text[:60] + "...") if len(full_text) > 60 else full_text
        logger.info(
            "[WhisperASR] lang=%s prob=%.2f dur=%.2fs ar=%s text=%r",
            info.language,
            info.language_probability,
            info.duration,
            is_likely_arabic,
            preview,
        )

        return Transcription(
            text=full_text,
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration,
            segments=segments,
            is_confident=is_confident,
            is_likely_arabic=is_likely_arabic,
        )


__all__ = [
    "WhisperASR",
    "Transcription",
    "Segment",
    "AudioInput",
    "MIN_LANGUAGE_CONFIDENCE",
    "DEFAULT_ARABIC_INITIAL_PROMPT",
]
