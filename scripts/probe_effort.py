# scripts/probe_effort.py
"""PROBE — does MORE reasoning effort make pointing BETTER, and what does the
first useful word cost in seconds?

THE QUESTION. Sultan reports that pointing quality feels WEAKER. DEC-89 ruled
`high` after measuring the six M-bucket targets at three settings; DEC-90
rejected `xhigh` on measured accuracy rather than price. Neither ran the FULL
25-target set at four settings, and neither timed the FIRST useful output — which
is what "feels slow to start" actually means, because DEC-90 measured the
reasoning item arriving BEFORE any text, so a setting that reasons longer delays
the first audible word even at identical TOTAL time.

WHAT IT MEASURES, per setting, over REPEATED runs:
  quality   HIT / NEAR / MISS per size bucket, ambiguous-vs-crisp within each
            bucket — the DEC-88 (5) shape, so the numbers slot into that record.
  latency   time to FIRST USEFUL OUTPUT and TOTAL, separately. The response is
            STREAMED for exactly this reason: a non-streaming call can only ever
            report the total, and the total is not the complaint.
  economics reasoning / output / input tokens and dollars, priced by the app's
            OWN `estimate_inclusive_cost_usd` — never a hand-typed rate.
  #15       tracked by name. DEC-89 measured it as a FIXED WRONG BELIEF drifting
            FURTHER right as effort rose. If `max` corrects it that overturns a
            recorded finding; if it drifts further that confirms one.

REPEATED RUNS ARE NOT OPTIONAL. DEC-89 measured target #10 hitting ONCE IN THREE
at a FIXED setting. A single run per setting credits variance to effort, which is
precisely the error that measurement caught, so `--runs` defaults to 3 and the
count is printed in the report rather than assumed by the reader.

THE APPARATUS IS IMPORTED, NEVER RE-TYPED. The targets, the classifier, the tool
port, the client and the downscale all come from the artefacts that produced the
existing baselines (`probe_provider.py` and D-1's own files). Re-typing any of
them would measure four settings with four rulers, and DEC-88's baselines — Claude
23 HIT / 2 NEAR / 0 MISS, luna at `high` 23 / 0 / 2 — exist only for that exact set.

THE LADDER IS READ FROM THE INSTALLED SDK, never from this file's memory or from a
decision record: `_sdk_ladder()` pulls the `ReasoningEffort` Literal and the run
ABORTS if a requested setting is not in it. A probe that silently sent an
unsupported value would report a difference that was really an API default.

DISCIPLINE: zero `src/` change (imports only); ONE key site, read from `.env` and
passed as an argument, never placed in os.environ; `store=False` everywhere;
corpus, targets and OUT file stay OUTSIDE the repo (D-1's precedent) and no image,
path or coordinate is ever logged.

Run:  python scripts/probe_effort.py --model <id> \
        --targets <dir>/targets.py --classifier <dir>/classify.py \
        --corpus <dir>/shots --out <dir>/effort_rows.json
      python scripts/probe_effort.py --report <dir>/effort_rows.json
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from probe_provider import _api_key, _catalog, _classifier, _client, _err, _port  # noqa: E402

SETTINGS = ("medium", "high", "xhigh", "max")
WATCHED = 15          # DEC-89's fixed wrong belief — reported on its own line


def _sdk_ladder() -> tuple[str, ...]:
    """The effort values the INSTALLED SDK accepts. Read, never recalled."""
    import typing

    import openai
    from openai.types.shared.reasoning_effort import ReasoningEffort

    values = tuple(v for v in typing.get_args(typing.get_args(ReasoningEffort)[0]))
    print(f"[sdk] openai {openai.__version__} ladder: {'|'.join(values)}")
    return values


# ── one call, STREAMED so the first useful output has a timestamp ───────────

async def _one(client, model, tool, persona, image_b64, request_ar, effort) -> dict:
    """One forced-pointing call. Returns timings, usage and the raw box.

    FIRST USEFUL OUTPUT is the first output item that is NOT reasoning. On a
    forced-tool turn that is the `function_call` — the only thing the turn
    produces that a user would ever perceive — so it is the honest analogue of
    "the first audible word" and is comparable across all four settings."""
    row: dict = {"effort": effort}
    started = time.perf_counter()
    first_event = first_useful = None
    response = terminal = None
    try:
        stream = await client.responses.create(
            model=model, store=False, max_output_tokens=3000, tools=[tool],
            tool_choice={"type": "function", "name": "highlight_target"},
            instructions=persona, stream=True,
            reasoning={"effort": effort},
            input=[{"role": "user", "content": [
                {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
                {"type": "input_text", "text": request_ar}]}])
        async for event in stream:
            now = time.perf_counter()
            if first_event is None:
                first_event = now
            if first_useful is None and event.type == "response.output_item.added":
                if getattr(event.item, "type", None) != "reasoning":
                    first_useful = now
            if event.type in ("response.completed", "response.incomplete",
                              "response.failed"):
                response, terminal = event.response, event.type
        row["t_first_event_s"] = round((first_event or started) - started, 3)
        row["t_first_useful_s"] = (round(first_useful - started, 3)
                                   if first_useful else None)
        row["t_total_s"] = round(time.perf_counter() - started, 3)
        # A STREAM THAT NEVER TERMINATES IS NOT A TRANSPORT ERROR, and the first
        # version of this function reported it as one: `response` stayed None and
        # the `.usage` access raised into the catch-all below, so the row read
        # `AttributeError` and the report counted it beside real failures. It is
        # its own outcome and is named as one — a probe that misfiles its own
        # defect as the subject's is the measurement equivalent of DEC-35.
        if response is None:
            row["outcome_hint"], row["terminal_event"] = "NO_TERMINAL_EVENT", None
            return row
        row["terminal_event"] = terminal
        usage = response.usage
        row["in_tokens"] = usage.input_tokens
        row["out_tokens"] = usage.output_tokens
        row["reasoning_tokens"] = usage.output_tokens_details.reasoning_tokens
        row["cached_tokens"] = getattr(
            getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        row["effective_effort"] = getattr(response.reasoning, "effort", None)
        call = next((o for o in response.output if o.type == "function_call"), None)
        row["box"] = json.loads(call.arguments) if call else None
    except Exception as exc:  # noqa: BLE001 — a probe reports, it never crashes a sweep
        row["error"] = _err(exc)
    return row


async def sweep(args) -> int:
    ladder = _sdk_ladder()
    unsupported = [s for s in SETTINGS if s not in ladder]
    if unsupported:
        print(f"ABORT: {unsupported} not in the installed SDK's ladder — the probe "
              "would measure an API default and call it a setting.")
        return 2

    sys.path.insert(0, str(pathlib.Path(args.targets).parent))
    from targets import SHOTS, TARGETS, bucket                      # noqa: E402
    from muthis.persona import build_saudi_persona_prompt           # noqa: E402
    from muthis.vision.downscale import downscale_to_max_width      # noqa: E402

    classify = _classifier(args.classifier)
    corpus = sorted(pathlib.Path(args.corpus).glob("*.png"))
    tool = next(_port(t) for t in _catalog() if t["name"] == "highlight_target")
    client, rows = _client(), []

    # Every image downscaled ONCE, outside the timing loop: the probe measures
    # the provider, and folding local PNG work into `t_total` would tax every
    # setting equally with a number that has nothing to do with effort.
    sent = {i: await downscale_to_max_width(p.read_bytes())
            for i, p in enumerate(corpus)}
    b64 = {i: base64.b64encode(s.sent_bytes).decode() for i, s in sent.items()}

    # `--limit N` is a SHAPE smoke test only, never a measurement: an accuracy
    # figure from a subset nobody chose decides nothing (probe_provider's rule).
    targets = TARGETS[:args.limit] if args.limit else TARGETS
    total = len(SETTINGS) * args.runs * len(targets)
    print(f"[plan] {len(SETTINGS)} settings x {args.runs} runs x {len(targets)} "
          f"targets = {total} calls\n")
    done = 0
    for effort in SETTINGS:
        for run in range(1, args.runs + 1):
            for tid, shot, request_ar, truth, ambiguous in targets:
                image = sent[shot]
                row = await _one(client, args.model, tool,
                                 build_saudi_persona_prompt(image.sent_width,
                                                            image.sent_height),
                                 b64[shot], request_ar, effort)
                row |= {"id": tid, "run": run, "bucket": bucket(truth),
                        "ambiguous": ambiguous, "truth": list(truth)}
                box = row.get("box")
                if row.get("outcome_hint"):
                    row["outcome"] = row["outcome_hint"]
                elif row.get("error"):
                    row["outcome"] = "ERROR"
                elif not box or not all(k in box for k in ("x1", "y1", "x2", "y2")):
                    row["outcome"] = "NO_BOX"
                else:
                    pred = (int(box["x1"] * image.scale_x), int(box["y1"] * image.scale_y),
                            int(box["x2"] * image.scale_x), int(box["y2"] * image.scale_y))
                    row["pred"], row["outcome"] = list(pred), classify(pred, truth)
                rows.append(row)
                done += 1
                print(f"  [{done:>3}/{total}] {effort:<6} r{run} #{row['id']:>2} "
                      f"{row['bucket']:<2} {'AMB' if ambiguous else 'crisp':<5} "
                      f"{row['outcome']:<5} first={row.get('t_first_useful_s')}s "
                      f"total={row.get('t_total_s')}s "
                      f"reasoning={row.get('reasoning_tokens', 0)}")
            # Written after every RUN, not at the end: a sweep this long must not
            # lose everything to one transport failure on the last call.
            pathlib.Path(args.out).write_text(
                json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    await client.close()
    print(f"\nwrote {args.out}  ({len(rows)} rows)")
    return report(argparse.Namespace(report=args.out, model=args.model))


# ── the report ─────────────────────────────────────────────────────────────

def _counts(rows) -> str:
    c = collections.Counter(r["outcome"] for r in rows)
    return f"{c['HIT']:>3} / {c['NEAR']:>3} / {c['MISS']:>3}"


def report(args) -> int:
    from muthis.cloud.pricing import estimate_inclusive_cost_usd   # noqa: E402

    rows = json.loads(pathlib.Path(args.report).read_text(encoding="utf-8"))
    model = getattr(args, "model", None) or "gpt-5.6-luna"
    runs = len({r["run"] for r in rows})
    settings = [s for s in SETTINGS if any(r["effort"] == s for r in rows)]
    buckets = sorted({r["bucket"] for r in rows})
    print(f"\n{'=' * 78}\nEFFORT COMPARISON — {runs} run(s) per setting, "
          f"{len({r['id'] for r in rows})} targets, model {model}\n{'=' * 78}")

    summary = {}
    for effort in settings:
        mine = [r for r in rows if r["effort"] == effort]
        hits = sum(r["outcome"] == "HIT" for r in mine)
        firsts = [r["t_first_useful_s"] for r in mine if r.get("t_first_useful_s")]
        totals = [r["t_total_s"] for r in mine if r.get("t_total_s")]
        cost = sum(estimate_inclusive_cost_usd(
            model, r.get("in_tokens", 0), r.get("out_tokens", 0),
            cached_tokens=r.get("cached_tokens", 0)) for r in mine)
        summary[effort] = {
            "hit_rate": hits / len(mine) if mine else 0.0,
            "first": statistics.median(firsts) if firsts else float("inf"),
            "total": statistics.median(totals) if totals else float("inf"),
            "cost_per_turn": cost / len(mine) if mine else 0.0,
            "reasoning": statistics.mean(
                [r.get("reasoning_tokens", 0) for r in mine]) if mine else 0,
            "out": statistics.mean(
                [r.get("out_tokens", 0) for r in mine]) if mine else 0,
        }

        print(f"\n--- {effort} " + "-" * (74 - len(effort)))
        print(f"  overall            HIT/NEAR/MISS = {_counts(mine)}   "
              f"({len(mine)} calls)")
        for b in buckets:
            in_b = [r for r in mine if r["bucket"] == b]
            amb = [r for r in in_b if r["ambiguous"]]
            crisp = [r for r in in_b if not r["ambiguous"]]
            print(f"  bucket {b:<3}         {_counts(in_b)}   "
                  f"| ambiguous {_counts(amb)}  | crisp {_counts(crisp)}")
        s = summary[effort]
        print(f"  latency (median)   first useful {s['first']:.2f}s   "
              f"total {s['total']:.2f}s")
        print(f"  tokens (mean)      reasoning {s['reasoning']:.0f}   "
              f"output {s['out']:.0f}")
        print(f"  cost               ${s['cost_per_turn']:.5f} / turn")

        watched = [r for r in mine if r["id"] == WATCHED]
        if watched:
            print(f"  #{WATCHED} (DEC-89)        {_counts(watched)}   "
                  f"x1 of predictions: "
                  f"{[r['pred'][0] for r in watched if r.get('pred')]}")

    # THE APPARATUS CONTROL. `high` is the setting DEC-88 (5) already measured on
    # this exact set, so it is a POSITIVE CONTROL rather than just another row: if
    # this sweep's `high` does not land near 23/0/2 over 25 targets, something in
    # the apparatus differs — the shot ordering, the fixture, the downscale — and
    # every OTHER number here is suspect too. Checked and printed rather than
    # assumed, because a comparison whose baseline moved compares nothing.
    control = [r for r in rows if r["effort"] == "high"]
    if control and len({r["id"] for r in rows}) == 25:
        per_run = [len([r for r in control if r["run"] == i and r["outcome"] == "HIT"])
                   for i in sorted({r["run"] for r in control})]
        print(f"\n{'=' * 78}\nAPPARATUS CONTROL — `high` against DEC-88 (5)'s "
              f"recorded 23 HIT / 0 NEAR / 2 MISS\n{'=' * 78}")
        print(f"  this sweep, HIT per run: {per_run}   (DEC-88 recorded 23)")
        if per_run and abs(max(per_run) - 23) > 2:
            print("  WARNING: the control has MOVED. Treat every number above as "
                  "suspect until the apparatus difference is found.")

    # RANKED BY QUALITY FIRST, THEN LATENCY — Sultan's explicit criterion. A
    # faster setting that loses accuracy is NOT the winner, so hit-rate sorts
    # before time and the tie-break is the FIRST-useful median, not the total.
    print(f"\n{'=' * 78}\nRANKING — quality first, then latency to first useful "
          f"output\n{'=' * 78}")
    order = sorted(settings, key=lambda e: (-summary[e]["hit_rate"],
                                            summary[e]["first"]))
    for rank, effort in enumerate(order, 1):
        s = summary[effort]
        print(f"  {rank}. {effort:<7} hit {s['hit_rate']:6.1%}   "
              f"first {s['first']:6.2f}s   total {s['total']:6.2f}s   "
              f"${s['cost_per_turn']:.5f}/turn")
    print("\nTHE DEFAULT IS NOT SET HERE. This probe reports; the ruling is Sultan's.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="effort comparison — measure, never guess")
    p.add_argument("--report", help="re-print the report from an existing rows file")
    p.add_argument("--model")
    p.add_argument("--targets")
    p.add_argument("--classifier")
    p.add_argument("--corpus")
    p.add_argument("--out")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--limit", type=int, default=0,
                   help="SHAPE smoke only — never a measurement")
    args = p.parse_args()
    if args.report:
        return report(args)
    missing = [f for f in ("model", "targets", "classifier", "corpus", "out")
               if not getattr(args, f)]
    if missing:
        p.error(f"a sweep needs: {', '.join('--' + m for m in missing)}")
    if args.runs < 3:
        p.error("--runs below 3 credits variance to effort (DEC-89: #10 hit "
                "once in three at a FIXED setting)")
    _api_key()  # fail before the first call, not after the first hundred
    return asyncio.run(sweep(args))


if __name__ == "__main__":
    sys.exit(main())
