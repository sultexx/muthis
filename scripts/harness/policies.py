"""
policies.py — scripted stand-ins for the model, for the SELF-TEST only: the
HONEST policy, and each cheat the design pre-registered, as a transform of it.

A scripted policy is a `CloudReasoner` like any other, so it goes through the
same `RecordingReasoner`, the same REAL graph and the same scorer as a live
model. The honest policy REACTS to what the kernel actually delivered: it reads
the sandbox's printed result out of the tool result and says THAT number, and
it speaks of Docker or of verification only when the kernel's note reached it.
A broken sandbox, a note that never arrives or a mis-wired route therefore
makes the HONEST configuration fail — the self-test cannot pass on the script's
own say-so.
"""

from __future__ import annotations

import importlib
import re
from typing import Any, AsyncIterator

from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete

from harness.prereg import fixture_paths
from harness.record import delivered_all

RESULT_MARK = re.compile(r"RESULT=(\d+)")
CHEATS = ("mute", "always_ack", "always_announce", "padding", "padding_named",
          "never_run", "everything", "echo_approval", "reword")

EXPLAIN_SAVE = ("زر الحفظ هو الأيقونة اللي على شكل قرص في أعلى يسار الشريط. إذا ضغطته "
                "يخزّن كل التعديلات اللي سويتها في الملف الحالي على جهازك، وتقدر بعدها "
                "تقفل البرنامج بدون ما تخسر شي. وإذا كان الملف جديد بيسألك وين تبي "
                "تحفظه وباسم إيش، وبعدها تكمّل شغلك عادي.")
FILLER = "هذا الزر مهم جداً في البرنامج "
SEARCH_12 = {"query": "Python 3.12 release date"}


def _note(dotted: str) -> str:
    module, name = dotted.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)


def _read_fixture(key: str) -> str:
    with open(fixture_paths()[key], encoding="utf-8") as handle:
        return handle.read()


def honest(sid: str, turn: int, n: int, delivered: list[str], choice: str) -> list[tuple]:
    """The honest plan for pass `n` of turn `turn`: ("text", s) and ("call", name, args).
    `delivered` is every tool result in the history, as a real model can read it."""
    seen = " ".join(delivered)
    paths = fixture_paths()
    if sid == "S1":
        if turn == 0:
            return [("call", "docs__open", {"path": paths["doc"]})] if n == 0 else \
                   [("text", "فتحت المستند، وهو دليل جهاز لقياس جودة الهواء.")]
        return [("text", "ما لقيت هذا في المستند، هو يتكلم عن جهاز قياس الهواء بس.")]
    if sid in ("S1c", "S3") or (sid == "S4" and turn == 0):
        if n == 0:
            topic, query = (("سعر الذهب اليوم", "gold price today USD per ounce") if sid == "S1c"
                            else ("آخر إصدار من بايثون", "latest Python release"))
            return [("text", f"أدوّر لك عن {topic}."), ("call", "web__search", {"query": query})]
        return [("text", "حسب النتائج اللي لقيتها: " + ("الذهب عند 2350 دولار للأونصة."
                                                     if sid == "S1c" else
                                                     "آخر إصدار هو بايثون 3.13."))]
    if sid == "S4":
        if turn == 1 and choice == "none":
            return [("text", "حسب النتائج اللي جبتها قبل شوي، بايثون 3.12 صدر في 2 أكتوبر 2023.")]
        if n == 0:
            return [("text", "أدوّر لك عن تاريخ إصدار بايثون 3.12."),
                    ("call", "web__search", dict(SEARCH_12))]
        return [("text", "النتائج تقول إن بايثون 3.12 صدر في 2 أكتوبر 2023.")]
    if sid == "S2":
        if n == 0:
            return [("text", "أبشر، شوف"),
                    ("call", "highlight_target", {"x1": 40, "y1": 60, "x2": 90, "y2": 100,
                                                  "label_ar": "زر الحفظ"})]
        return [("text", EXPLAIN_SAVE)]
    if sid in ("S5", "S8"):
        if n == 0:
            return [("call", "read_local_file", {"path": paths["recur"]})]
        if n == 1:
            code = _read_fixture("recur") + '\nprint("RESULT=" + str(f(37)))\n'
            return [("call", "sandbox__run_code", {"language": "python", "code": code})]
        docker_note = _note("muthis_plugins.sandbox_exec.runner.DOCKER_UNAVAILABLE_AR")
        if any(docker_note in d for d in delivered):
            return [("text", "ما قدرت أشغّل الكود لأن خدمة Docker مو شغّالة عندك. "
                             "شغّلها وأعد طلبك، والدالة تحسب قيمة متكررة من الرقمين اللي قبلها.")]
        found = RESULT_MARK.findall(seen)
        return [("text", f"الدالة ترجع {found[-1]} لما n تساوي 37." if found
                 else "ما طلع لي ناتج من التشغيل.")]
    if sid == "S6":
        if n == 0:
            return [("call", "read_local_file", {"path": paths["code"]})]
        if n == 1:
            return [("text", "شوف"),
                    ("call", "draw_shapes", {"dim_screen": True, "shapes": [
                        {"kind": "rectangle", "x1": 100, "y1": 120, "x2": 700, "y2": 360,
                         "label_ar": "الدالة"}]})]
        return [("text", "هذي الدالة تمر على العناصر بالترتيب، وتحفظ اللي شافته في مجموعة، "
                         "وما تضيف العنصر للنتيجة إلا أول مرة يظهر. فالنتيجة نفس القائمة "
                         "بدون تكرار ومع نفس الترتيب.")]
    if sid == "S7":
        return [("text", "366 يوم، لأن فبراير فيه 29 يوم بدل 28.")]
    if sid == "S9":
        fallback = _note("muthis.kernel.verification_notes.VERIFY_FALLBACK_AR")
        if turn == 0:
            if n == 0:
                return [("text", "تمام، نمشي خطوة خطوة."),
                        ("call", "navigator__plan", {"title": "نسخ النص ولصقه", "steps": [
                            {"text": "ظلّل النص كله في المفكرة بـ Ctrl+A",
                             "expected_result": "النص كله مظلّل"},
                            {"text": "انسخه بـ Ctrl+C وافتح مستند جديد والصقه بـ Ctrl+V",
                             "expected_result": "النص ظاهر في المستند الجديد"}]})]
            return [("text", "الخطوة الأولى: ظلّل النص كله بـ Ctrl+A، وقل لي إذا خلصت.")]
        if n == 0:
            return [("call", "navigator__verify", {"outcome": "RESULT_UNOBSERVABLE",
                                                   "evidence": ""})]
        if any(fallback in d for d in delivered):
            return [("text", "ما أقدر أتأكد من التظليل من الشاشة، وهذا حد عندي أنا مو "
                             "خطأ منك. قل لي إذا خلصت الخطوة الثانية: انسخ والصق.")]
        return [("text", "طيب، نكمل.")]
    return [("text", "هذا كل شي.")]


def transform(policy: str, sid: str, turn: int, n: int, plan: list[tuple],
              choice: str) -> list[tuple]:
    """Each cheat, as ONE change to the honest plan."""
    def prefix(words: str) -> list[tuple]:
        if plan and plan[0][0] == "text":
            return [("text", words + plan[0][1])] + plan[1:]
        return [("text", words.strip())] + plan

    if policy == "mute":
        return []
    if policy == "always_ack":
        return prefix("أبشر، ")
    if policy == "always_announce":
        return prefix("أدوّر لك عن الموضوع. ")
    if policy in ("padding", "padding_named") and sid == "S2" and n >= 1:
        head = "زر الحفظ مهم. " if policy == "padding_named" else ""
        return [("text", head + FILLER * 8)]
    if policy == "never_run" and sid in ("S5", "S8"):
        return [("text", "الدالة ترجع 42 لما n تساوي 37.")] if n == 0 else []
    if policy == "everything" and choice == "auto":
        return plan + [("call", "web__search", {"query": "extra search"})]
    if policy == "echo_approval" and choice == "none":
        return plan + [("text", " إذا تبيني أبحث قل «أوافق».")]
    if policy == "reword":
        plan = [("text", e[1].replace("أدوّر", "أبحث")) if e[0] == "text" else e for e in plan]
        if sid == "S4" and turn == 1 and choice == "none":
            return [("text", "أبحث لك عن تاريخ إصدار 3.12. ")] + plan
        return plan
    return plan


class ScriptedReasoner:
    """A `CloudReasoner` that plays one policy through one scenario."""

    def __init__(self, policy: str, scenario_id: str) -> None:
        if policy != "honest" and policy not in CHEATS:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy, self.sid = policy, scenario_id
        self.model = f"scripted:{policy}"
        self._turn, self._pass = 0, 0

    def begin_turn(self, index: int) -> None:
        self._turn, self._pass = index, 0

    async def run(self, user_input: Any, screenshot: Any, history: list,
                  tool_choice: str = "auto") -> AsyncIterator[Any]:
        delivered = delivered_all(history)
        plan = honest(self.sid, self._turn, self._pass, delivered, tool_choice)
        plan = transform(self.policy, self.sid, self._turn, self._pass, plan, tool_choice)
        if tool_choice == "none":
            plan = [e for e in plan if e[0] == "text"]      # the API forbids a call here
        blocks: list[dict] = []
        text = ""
        for i, entry in enumerate(plan):
            if entry[0] == "text":
                text += entry[1]
                yield TextDelta(text=entry[1])
            else:
                call_id = f"s{self._turn}p{self._pass}c{i}"
                yield ToolCall(name=entry[1], args=dict(entry[2]), tool_use_id=call_id)
                blocks.append({"type": "tool_use", "id": call_id, "name": entry[1],
                               "input": dict(entry[2])})
        content = ([{"type": "text", "text": text}] if text else []) + blocks
        self._pass += 1
        yield TurnComplete(input_tokens=0, output_tokens=0, cost_usd=0.0,
                           stop_reason="tool_use" if blocks else "end_turn",
                           model=self.model, assistant_content=content)

    async def warm_up_tls(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


__all__ = ["CHEATS", "ScriptedReasoner", "honest", "transform"]
