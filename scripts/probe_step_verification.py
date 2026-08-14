# scripts/probe_step_verification.py
"""P0-Navigator-v2 — does the difference between two frames carry ENOUGH SIGNAL?

THE QUESTION, and it is narrower than "can the model tell?". Navigator v1 never
verifies that the user performed a step (DEFERRED at T4). v2 would, and Sultan's
binding condition is that the decision must NOT be "the model believes the step is
done" — it must be a measurable signal. Before any of that is designed, one thing
has to be true: the BEFORE/AFTER difference must carry signal at all. That is
measurable on STATIC PAIRS, with no capture mechanism, no persistence and no
privacy surface — so if the numbers fail, nothing was built and nothing was
touched.

WHAT IT MEASURES, per case, over REPEATED runs:
  detection    on CLEAR and SUBTLE, REPORTED SEPARATELY. Sultan named subtle
               completion as the boundary, and averaging it with the easy kind
               would hide exactly the number that decides the design.
  false advance on NO_CHANGE, WRONG_CHANGE and DISTRACTION — THE GOVERNING METRIC.
               A missed completion costs one F9 press. A false advance jumps the
               user to a step he has not reached and explains against a screen he
               is not looking at. They are not symmetric and are never averaged.
  cost/latency per verification, priced by the app's OWN `estimate_inclusive_cost_usd`
               — never a hand-typed rate. A window that fires after every step
               multiplies both.

THE ANSWER IS READ DETERMINISTICALLY, NEVER INTERPRETED. The model answers through
a FORCED function call with a three-value enum, so parsing cannot drift: the
API validates the shape and the probe reads a field. What the model SAYS (its
evidence sentence, its self-reported confidence) is recorded and printed as
OBSERVATION and never enters a score — the T6 split, deterministic where it can
be, observed where it cannot, never conflated. The verdicts are Sultan's labels
in `cases.py`; the model's answer is scored against them.

`unclear` IS ITS OWN OUTCOME and is never folded into `no`. It did not detect, so
it is not a detection; it would not advance, so it is not a false advance. Folding
it into `no` would flatter the governing metric by counting a shrug as a refusal —
and it is precisely the population the decision table's HALF-measure branch is about.

REPEATED RUNS, AND WHAT THEY DO AND DO NOT BUY. DEC-89 measured a target hitting
ONCE IN THREE at a FIXED setting, and DEC-98 showed instability moves between
subjects, so a single run per case would credit variance to signal. Sultan set
three as the minimum; the default here is TEN, and the reason is worth stating
precisely because it is easy to overclaim.

  runs buy STABILITY. At three runs the achievable false-advance rates over the
  five negative pairs step 0% -> 6.7% -> 13.3%, so NOTHING lands between zero and
  the 5% gate and one stochastic slip fails the whole feature. At ten runs a pair
  that advances one time in ten becomes visible instead of invisible.

  runs DO NOT buy COVERAGE. Repeated runs over the SAME five negative pairs are
  CLUSTERED, not independent, so a call-level confidence bound computed over 50
  observations flatters itself: the real uncertainty is whether five pairs
  represent the negative space, and no number of runs touches that. The report
  therefore prints the pair-level view beside the call-level one — how many
  DISTINCT pairs ever advanced — because that is the number that generalises,
  and prints the Clopper-Pearson bound with its clustering named rather than
  letting "we saw none" read as "there are none".

THE APPARATUS IS IMPORTED, NEVER RE-TYPED: the key site, the client and the error
formatter come from `probe_provider.py`, and frames go through the REAL
`downscale_to_max_width` at the REAL production width, so the model sees what a
verification window would actually be handed. Effort is `high` because that is
the RULED production value (DEC-89 ruling 2, upheld by DEC-98) and not a knob.

DISCIPLINE: zero `src/` change (imports only); ONE key site, read from `.env` and
passed as an argument, never placed in os.environ; `store=False` everywhere; the
cases, the frames and the OUT file stay OUTSIDE the repo (D-1's precedent) and no
image, no path and no frame content is ever written into the repo or a log.

Run:  python scripts/probe_step_verification.py --model gpt-5.6-luna \
        --cases <dir>/cases.py --frames <dir>/images --out <dir>/rows.json
      python scripts/probe_step_verification.py --report <dir>/rows.json
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import json
import math
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from probe_provider import _api_key, _client, _err  # noqa: E402

EFFORT = "high"          # the RULED production value, not a probe preference
ANSWERS = ("yes", "no", "unclear")

# The instruction is NEUTRAL AND SYMMETRIC ON PURPOSE. A verification window that
# ships would very likely be written conservatively, because false advance is the
# expensive error — but that is a PROMPT OPERATING POINT, and tuning one here
# would measure the tuning instead of the signal. The three outcomes are
# described in parallel, with no warning that traps exist and no suggestion that
# the user has just done the step. What a conservative prompt buys is untested
# and is named as such in the report.
INSTRUCTION = (
    "You are checking one step of a walkthrough on a Windows 11 desktop.\n"
    "You are given the step, then two screenshots of the same machine: the frame "
    "BEFORE the user was asked to carry it out, and the frame AFTER.\n"
    "Judge from the two frames whether that step was carried out.\n"
    "  yes      the AFTER frame shows the step was carried out\n"
    "  no       the AFTER frame shows the step was not carried out\n"
    "  unclear  the two frames do not settle it\n"
    "Call report_step_check exactly once."
)

TOOL = {
    "type": "function",
    "name": "report_step_check",
    "strict": False,
    "description": "Report whether the described step was carried out, judging "
                   "only from the BEFORE and AFTER frames.",
    "parameters": {
        "type": "object",
        "properties": {
            "completed": {"type": "string", "enum": list(ANSWERS)},
            "evidence": {"type": "string", "description":
                         "What in the AFTER frame differs from the BEFORE frame "
                         "and why it does or does not show the step was done."},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "required": ["completed", "evidence", "confidence"],
    },
}


def _cases(path: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location("_sv_cases", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _frame_b64(path: pathlib.Path) -> str:
    """The REAL production payload copy. The downscale returns the ORIGINAL bytes
    untouched when a frame is already within the width cap, so a JPEG fixture
    could silently ride out under a `data:image/png` label — asserted rather than
    assumed, DEC-11's failure class (a wire-format lie every offline check passes)."""
    from muthis.vision.downscale import downscale_to_max_width

    sent = await downscale_to_max_width(path.read_bytes())
    if not sent.sent_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        sys.exit(f"ABORT: {path.name} did not reach the payload as PNG — the "
                 "media type would be mislabelled on the wire.")
    return base64.b64encode(sent.sent_bytes).decode()


async def _one(client, model, step, before_b64, after_b64) -> dict:
    """One verification. Not streamed: a verdict has no partial value, so the
    honest latency for a window that must finish before advancing is the TOTAL."""
    row: dict = {}
    started = time.perf_counter()
    try:
        response = await client.responses.create(
            model=model, store=False, max_output_tokens=3000, tools=[TOOL],
            tool_choice={"type": "function", "name": "report_step_check"},
            instructions=INSTRUCTION, reasoning={"effort": EFFORT},
            input=[{"role": "user", "content": [
                {"type": "input_text", "text": f"STEP: {step}"},
                {"type": "input_text", "text": "BEFORE:"},
                {"type": "input_image",
                 "image_url": f"data:image/png;base64,{before_b64}"},
                {"type": "input_text", "text": "AFTER:"},
                {"type": "input_image",
                 "image_url": f"data:image/png;base64,{after_b64}"}]}])
        row["t_total_s"] = round(time.perf_counter() - started, 3)
        usage = response.usage
        row["in_tokens"] = usage.input_tokens
        row["out_tokens"] = usage.output_tokens
        row["reasoning_tokens"] = usage.output_tokens_details.reasoning_tokens
        row["cached_tokens"] = getattr(
            getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        # THE EFFORT THE API ACTUALLY APPLIED, read back rather than assumed. A
        # setting that is silently dropped would have this probe reporting a
        # provider DEFAULT as though it were the ruled `high` — probe_effort
        # guards the same way, and here it is load-bearing because the reasoning
        # count came back ZERO and only this field separates "high ran and
        # decided not to think" from "high never arrived".
        row["effective_effort"] = getattr(
            getattr(response, "reasoning", None), "effort", None)
        # A TRUNCATED CALL IS ITS OWN OUTCOME, not a refusal and not an error.
        # Reasoning bills as output, so a cap reached mid-thought yields no
        # function_call at all — reported as INCOMPLETE rather than misfiled as
        # the subject's failure (probe_effort's NO_TERMINAL_EVENT lesson).
        if response.status == "incomplete":
            row["answer"] = "INCOMPLETE"
            return row
        call = next((o for o in response.output if o.type == "function_call"), None)
        if call is None:
            row["answer"] = "NO_ANSWER"
            return row
        payload = json.loads(call.arguments)
        answer = str(payload.get("completed", "")).strip().lower()
        row["answer"] = answer if answer in ANSWERS else "INVALID"
        row["confidence"] = payload.get("confidence")      # OBSERVED, never scored
        row["evidence"] = str(payload.get("evidence", ""))[:600]
    except Exception as exc:  # noqa: BLE001 — a probe reports, it never crashes a sweep
        row["answer"], row["error"] = "ERROR", _err(exc)
        row.setdefault("t_total_s", round(time.perf_counter() - started, 3))
    return row


async def sweep(args) -> int:
    cases = _cases(args.cases)
    frames = pathlib.Path(args.frames)
    todo = list(cases.CASES) + list(cases.CONTROLS)
    if args.limit:
        todo = todo[:args.limit]

    missing = sorted({n for _, _, b, a, _ in todo for n in (b, a)
                      if not (frames / n).is_file()})
    if missing:
        sys.exit(f"ABORT: frames absent: {missing}. A case whose frame is missing "
                 "is UNAVAILABLE and is never substituted.")

    # Decoded ONCE, outside the timing loop: the probe measures the provider, and
    # folding local Pillow work into `t_total` would tax every call with a number
    # that has nothing to do with verification.
    names = sorted({n for _, _, b, a, _ in todo for n in (b, a)})
    b64 = {n: await _frame_b64(frames / n) for n in names}

    client, rows = _client(), []
    total = args.runs * len(todo)
    print(f"[plan] {len(todo)} cases x {args.runs} runs = {total} calls   "
          f"model={args.model} effort={EFFORT}\n")
    done = 0
    for run in range(1, args.runs + 1):
        for cid, kind, before, after, step in todo:
            row = await _one(client, args.model, step, b64[before], b64[after])
            row |= {"id": cid, "kind": kind, "run": run}
            row["scored"] = _scored(cases, kind, row["answer"])
            rows.append(row)
            done += 1
            print(f"  [{done:>3}/{total}] r{run} #{cid:<3} {kind:<17} "
                  f"{str(row['answer']):<10} {row['scored']:<10} "
                  f"conf={row.get('confidence')} {row.get('t_total_s')}s "
                  f"reasoning={row.get('reasoning_tokens', 0)}")
        # Written after every RUN: a sweep must not lose everything to one
        # transport failure on the last call.
        pathlib.Path(args.out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    await client.close()
    print(f"\nwrote {args.out}  ({len(rows)} rows)")
    return report(argparse.Namespace(report=args.out, model=args.model,
                                     cases=args.cases))


def _scored(cases, kind: str, answer: str) -> str:
    if answer not in ANSWERS:
        return "NO_READ"
    if kind in cases.POSITIVE_KINDS:
        return "DETECT" if answer == "yes" else "MISS"
    if kind in cases.NEGATIVE_KINDS:
        return "FALSE_ADV" if answer == "yes" else "HELD"
    return "CTRL_FAIL" if answer == "yes" else "CTRL_OK"      # the control


def _upper95(k: int, n: int) -> float:
    """Exact one-sided Clopper-Pearson 95% upper bound on a rate of k/n.

    Printed beside every rate because 'we observed none' is not 'there are none':
    at n=25 a clean sweep still admits a true rate near 11%, and a probe that let
    a point estimate stand alone would hand Sultan more certainty than it bought."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        cdf = sum(math.comb(n, i) * mid ** i * (1 - mid) ** (n - i)
                  for i in range(k + 1))
        lo, hi = (mid, hi) if cdf > 0.05 else (lo, mid)
    return hi


def _rate(rows, hit: str) -> tuple[int, int, float, float]:
    n = len(rows)
    k = sum(r["scored"] == hit for r in rows)
    return k, n, (k / n if n else 0.0), _upper95(k, n)


def _per_case(rows, ids) -> None:
    for cid in ids:
        mine = [r for r in rows if r["id"] == cid]
        if not mine:
            continue
        kind = mine[0]["kind"]
        seq = " ".join(f"{str(r['answer'])[:7]:<7}" for r in
                       sorted(mine, key=lambda r: r["run"]))
        conf = [r.get("confidence") for r in mine if r.get("confidence") is not None]
        median = statistics.median(conf) if conf else "-"
        print(f"    #{cid:<3} {kind:<17} {seq}  conf~{median}")


def report(args) -> int:
    from muthis.cloud.pricing import estimate_inclusive_cost_usd

    rows = json.loads(pathlib.Path(args.report).read_text(encoding="utf-8"))
    cases = _cases(args.cases)
    model = getattr(args, "model", None) or "gpt-5.6-luna"
    runs = len({r["run"] for r in rows})
    real = [r for r in rows if r["kind"] in cases.POSITIVE_KINDS
            or r["kind"] in cases.NEGATIVE_KINDS]
    pairs = len({r["id"] for r in real})

    print(f"\n{'=' * 78}\nP0-NAVIGATOR-V2 — STATIC STEP VERIFICATION\n{'=' * 78}")
    print(f"  model {model}   effort {EFFORT}   {runs} run(s)   "
          f"{pairs} pairs   {len(real)} scored calls")
    print(f"  pairs specified {cases.INTENDED_PAIRS}, constructible {pairs} "
          f"— SHORTFALL {cases.INTENDED_PAIRS - pairs}")
    print(f"  frames: {cases.FRAME_NOTE}")
    applied = collections.Counter(str(r.get("effective_effort")) for r in rows)
    print(f"  effort the API reported back: {dict(applied)}")
    if any(k not in (EFFORT, "None") for k in applied):
        print(f"  WARNING: an effort other than the ruled `{EFFORT}` was applied — "
              "these numbers describe a setting nobody chose.")

    # ── DETECTION, the two positive kinds kept apart ───────────────────────
    print(f"\n{'-' * 78}\nDETECTION — reported per kind, never averaged\n{'-' * 78}")
    det_rows = [r for r in real if r["kind"] in cases.POSITIVE_KINDS]
    for kind in sorted(cases.POSITIVE_KINDS):
        mine = [r for r in det_rows if r["kind"] == kind]
        if not mine:
            continue
        k, n, rate, _ = _rate(mine, "DETECT")
        unclear = sum(r["answer"] == "unclear" for r in mine)
        print(f"  {kind:<8} detected {k:>3}/{n:<3} = {rate:6.1%}   "
              f"(missed as `no` {sum(r['answer'] == 'no' for r in mine)}, "
              f"as `unclear` {unclear})")
        _per_case(mine, sorted({r["id"] for r in mine}))
    k, n, det_rate, _ = _rate(det_rows, "DETECT")
    print(f"  {'POOLED':<8} detected {k:>3}/{n:<3} = {det_rate:6.1%}")

    # ── FALSE ADVANCE, the governing metric ────────────────────────────────
    print(f"\n{'-' * 78}\nFALSE ADVANCE — THE GOVERNING METRIC\n{'-' * 78}")
    neg = [r for r in real if r["kind"] in cases.NEGATIVE_KINDS]
    for kind in sorted(cases.NEGATIVE_KINDS):
        mine = [r for r in neg if r["kind"] == kind]
        if not mine:
            continue
        k, n, rate, hi = _rate(mine, "FALSE_ADV")
        print(f"  {kind:<13} advanced {k:>3}/{n:<3} = {rate:6.1%}   "
              f"(95% upper {hi:.1%})")
        _per_case(mine, sorted({r["id"] for r in mine}))
    fa_k, fa_n, fa_rate, fa_hi = _rate(neg, "FALSE_ADV")
    print(f"  {'POOLED':<13} advanced {fa_k:>3}/{fa_n:<3} = {fa_rate:6.1%}   "
          f"(95% upper {fa_hi:.1%})")
    print(f"  held: `no` {sum(r['answer'] == 'no' for r in neg)}, "
          f"`unclear` {sum(r['answer'] == 'unclear' for r in neg)}")
    # THE PAIR-LEVEL VIEW, and it is the one that generalises. Repeated runs over
    # the same pairs are clustered, so the call-level rate above measures how
    # STABLE the model is on these five negatives — not how it behaves on the
    # negative space at large. A pair that advances even once is a pair with a
    # hole in it, and counting pairs rather than calls is what says so.
    neg_ids = sorted({r["id"] for r in neg})
    ever = [i for i in neg_ids
            if any(r["scored"] == "FALSE_ADV" for r in neg if r["id"] == i)]
    print(f"  PAIRS that EVER advanced: {len(ever)}/{len(neg_ids)}"
          f"{' — ' + str(ever) if ever else ''}")

    # ── the apparatus control ──────────────────────────────────────────────
    ctrl = [r for r in rows if r["kind"].startswith("CONTROL")]
    if ctrl:
        print(f"\n{'-' * 78}\nCONTROLS — scored apart, never folded into the "
              f"governing metric\n{'-' * 78}")
        for kind in sorted({r["kind"] for r in ctrl}):
            mine = [r for r in ctrl if r["kind"] == kind]
            bad = sum(r["scored"] == "CTRL_FAIL" for r in mine)
            note = {"CONTROL_IDENTICAL": "same frame twice, result absent",
                    "CONTROL_REVERSED": "completed frame as BEFORE — a "
                                        "difference-detector answers `yes`"}
            print(f"  {kind:<18} advanced {bad:>3}/{len(mine):<3} = "
                  f"{bad / len(mine):6.1%}   ({note.get(kind, '')})")
            _per_case(mine, sorted({r["id"] for r in mine}))
        if any(r["scored"] == "CTRL_FAIL" for r in ctrl):
            print("  WARNING: a control advanced. Treat every number above as "
                  "suspect until that is explained.")

    # ── cost, latency, and the answers the probe could not read ────────────
    ok = [r for r in real if r.get("t_total_s") and "error" not in r]
    lat = [r["t_total_s"] for r in ok]
    cost = [estimate_inclusive_cost_usd(model, r.get("in_tokens", 0),
                                        r.get("out_tokens", 0),
                                        cached_tokens=r.get("cached_tokens", 0))
            for r in ok]
    print(f"\n{'-' * 78}\nCOST AND LATENCY PER VERIFICATION\n{'-' * 78}")
    if lat:
        print(f"  latency   median {statistics.median(lat):.2f}s   "
              f"min {min(lat):.2f}s   max {max(lat):.2f}s")
        print(f"  cost      mean ${statistics.mean(cost):.5f} / verification   "
              f"-> ${statistics.mean(cost) * 6:.4f} over a 6-step walkthrough")
        print(f"  tokens    input {statistics.mean([r['in_tokens'] for r in ok]):.0f}"
              f"   reasoning "
              f"{statistics.mean([r.get('reasoning_tokens', 0) for r in ok]):.0f}"
              f"   cached "
              f"{statistics.mean([r.get('cached_tokens', 0) for r in ok]):.0f}")
    unread = collections.Counter(r["answer"] for r in real
                                 if r["answer"] not in ANSWERS)
    print(f"  unreadable calls: {dict(unread) or 'none'}")

    # OBSERVATION ONLY. Self-reported confidence is exactly the "the model
    # believes" quantity Sultan ruled out of the decision, so it is printed
    # beside the outcomes and never gates one. If a later design wants a
    # confidence threshold it buys its own measurement.
    print(f"\n  confidence (OBSERVED, never a verdict):")
    for label, sub in (("detected", [r for r in det_rows if r["scored"] == "DETECT"]),
                       ("missed", [r for r in det_rows if r["scored"] == "MISS"]),
                       ("false advances", [r for r in neg if r["scored"] == "FALSE_ADV"]),
                       ("held", [r for r in neg if r["scored"] == "HELD"])):
        vals = [r["confidence"] for r in sub if r.get("confidence") is not None]
        print(f"    {label:<15} n={len(sub):<3} median "
              f"{statistics.median(vals) if vals else '-'}")

    # ── the table, written BEFORE the measurement ──────────────────────────
    print(f"\n{'=' * 78}\nTHE DECISION TABLE — Sultan's, fixed before these numbers "
          f"existed\n{'=' * 78}")
    print("  detection >=90% AND false advance <=5%  -> v2 FEASIBLE; design it")
    print("  false advance >5%                       -> STOP v2, move to Code "
          "Intelligence")
    print("  detection <90% with low false advance   -> HALF measure: it OFFERS, "
          "never advances")
    subtle = [r for r in det_rows if r["kind"] == "SUBTLE"]
    _, _, subtle_rate, _ = _rate(subtle, "DETECT")
    # An empty kind prints `-`, never `0.0%`: a rate over zero observations is
    # not a low score, and DEC-50's rule is that a check which examined nothing
    # must never look like a check that failed — or passed.
    subtle_txt = f"{subtle_rate:.1%}" if subtle else "- (not measured)"
    print(f"\n  measured: detection pooled {det_rate:.1%} "
          f"(SUBTLE alone {subtle_txt}), false advance {fa_rate:.1%} "
          f"[{fa_k}/{fa_n}]")
    if fa_rate > 0.05:
        landing = "row 2 — false advance is above the gate"
    elif det_rate >= 0.90:
        landing = "row 1 — both conditions met"
    else:
        landing = "row 3 — the gate holds but detection is short"
    print(f"  the arithmetic lands in {landing}.")
    if fa_n:
        print(f"\n  POWER, stated so the gate is not over-read:")
        print(f"    {fa_n} negative calls over {len(neg_ids)} distinct negative "
              f"pairs; the call-level gate cannot resolve below {1 / fa_n:.1%}.")
        print(f"    Those calls are CLUSTERED on {len(neg_ids)} pairs, so the "
              f"{fa_hi:.1%} bound is optimistic — it prices stochastic wobble, "
              "not whether five pairs represent the negative space.")
        print(f"    Treated as {len(neg_ids)} independent pairs instead, a clean "
              f"sweep admits a true pair-level failure rate up to "
              f"{_upper95(len(ever), len(neg_ids)):.1%}.")
    print("\nTHIS PROBE REPORTS. THE RULING IS SULTAN'S.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="P0 step verification — measure, never guess")
    p.add_argument("--report", help="re-print the report from an existing rows file")
    p.add_argument("--model")
    p.add_argument("--cases", help="path to the OUT-OF-REPO cases.py manifest")
    p.add_argument("--frames", help="path to the OUT-OF-REPO frames directory")
    p.add_argument("--out")
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--limit", type=int, default=0,
                   help="SHAPE smoke only — never a measurement")
    args = p.parse_args()
    if args.report:
        if not args.cases:
            p.error("--report needs --cases: the labels are not in the rows file")
        return report(args)
    missing = [f for f in ("model", "cases", "frames", "out") if not getattr(args, f)]
    if missing:
        p.error(f"a sweep needs: {', '.join('--' + m for m in missing)}")
    if args.runs < 3:
        p.error("--runs below 3 credits variance to signal (DEC-89: a target hit "
                "once in three at a FIXED setting)")
    if pathlib.Path(args.out).resolve().is_relative_to(ROOT):
        p.error("--out must live OUTSIDE the repo: the rows carry the model's "
                "descriptions of Sultan's screen")
    _api_key()  # fail before the first call, not after the first fifty
    return asyncio.run(sweep(args))


if __name__ == "__main__":
    sys.exit(main())
