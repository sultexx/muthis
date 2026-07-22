# Phase 2 — Milestone 1 Closure Report (`sandbox_exec` — the isolated sandbox)

- **Project:** Mut'his V2
- **Milestone:** Phase 2, Milestone 1 — `sandbox_exec` (`sandbox__run_code`)
- **Branch:** `feature/v2-phase2-sandbox` (cut from `main` at `637c687`; **main untouched**)
- **Status:** **CLOSED — signed off by Sultan's personal Live SOP run, 2026-07-22.** The merge to `main` is his to run (not performed here).
- **Written:** 2026-07-22 (English, all-ASCII UTF-8 — committed to git)
- **Authority:** `DECISIONS.md` (DEC-3, DEC-8..DEC-13) + the milestone commits below. This report certifies closure; it is not itself a decision.

> This report certifies that Phase 2, Milestone 1 closed correctly: the sandbox
> executes model code in an isolated, throwaway container behind the
> `sandbox.execute` capability; the sealed kernel never learned the word
> "Docker"; the draw path was never touched; the primary security guard was
> proven DETERMINISTICALLY on real hardware; and Sultan signed off in person by
> eye, ear, and the printed summary — the only acceptance an execution milestone
> can have (project law).

---

## 1. Verdict

`sandbox_exec` is COMPLETE. The model can now call `sandbox__run_code` to run a
short snippet in an isolated container (no network, no host filesystem,
unprivileged, read-only rootfs, resource-capped, destroyed after the run) and
read the REAL output back — the FIRST execution capability in a product that was
LOOK-only, delivered without weakening a single LOOK-only guarantee. The live
SOP passed all checks on Sultan's machine; his personal sign-off closes the
milestone.

## 2. Implementation — risk-ordered gates P0 → T6

Each gate ended with a STOP for Sultan's approval before the next; no gate
auto-continued. Detail lives in `DECISIONS.md` and the commit bodies.

| Gate | Commit(s) | Summary |
|---|---|---|
| P0 Docker probe | (scratchpad, not committed) | Warm create→start→wait→rm ≈493 ms; ALL DEC-3 flags apply AND bite (uid 65534, net blocked, root read-only, /work writable); `docker kill` from a separate thread = 105 ms → exit 137. GATE PASS. |
| T1 contract | `b72dac8` | `src/muthis_plugins/sandbox_exec/` — the `run_code` §2.1 contract + stateless declaration skeleton. ADMISSIBLE. |
| DEC-8→finding→DEC-9 | `3db4888`, `023e869`, `3f14476` | Staging ruling: `docker cp` proved incompatible with `--read-only` (live) → superseded by a stdin BOOTSTRAP into the tmpfs `/work` (no cp, every DEC-3 flag kept). |
| T2 runner | `dedfb15` | `runner.py` + `docker_cmd.py` + `bootstrap.py` — one container lifecycle over injected asyncio-subprocess + FileReader-gate seams; bounded 64 KiB ANSI-stripped tails; wall timeout → `docker kill` → `rm -f` always; NEVER raises. |
| T3 SandboxGate | `183b597` | The per-turn ≤3-runs limiter (DEC-3-B), FULLY decoupled from `HighlightGate` (its own object, imports nothing from the kernel); the 4th run gets an internal-directive refusal. |
| T4 on_interrupt hook | `ff52a3e` | `kernel/interrupt_hooks.py` — the generic `on_interrupt` hook (DEC-3-C, the ONE kernel touch); fire-and-forget on daemon threads; the kernel names neither "docker" nor "sandbox". Orchestrator stayed ≤300 by extraction. |
| DEC-10 + T5 wiring | `24b8486`, `d249447`, `aee3608` | Confirmation path DEFERRED to `web_research` (no trigger this milestone). `run_code` is SERVICED end-to-end: declaration plugin mounted namespaced → JOINS the model catalog (byte-pinned `look_tools_v2.json`, the FIRST model-visible change since Phase 1); `turn_pass` services it after the sync point (like read, never the draw gate); F9 kills the live container via the T4 hook. |
| Ceiling debt | `d596115` | `orchestrator.py` at 299/300 logged as a TRACKED constraint — extract before any future touch. |
| T6 live SOP | `2a2975d`, `16afd45`, `f336801`, `574287c` | The diagnostic + the three fixes the live run forced (see §3). |

## 3. The live SOP — what it caught, and the sign-off

The T6 diagnostic (`scripts/diag_sandbox.py`) drove real `run_code` turns on
real Docker. It did its job: it caught two REAL defects that unit tests had not,
each fixed under a logged ruling before the next run.

1. **DEC-11 (`16afd45`) — the Anthropic 400.** The first run failed at CHECK 1:
   ruling C-3's dot-namespacing (`sandbox.run_code`) violates the tool-name
   pattern `^[a-zA-Z0-9_-]{1,128}$`. `sandbox.run_code` was the first namespaced
   tool ever shown to the model, so the clash was latent until a live run.
   Fixed: namespaced tools use `__` (`sandbox__run_code`); the separator lives in
   ONE place (`tool_router.namespaced_name`); a NEW guard test validates EVERY
   catalog name against the pattern — the missing guard was the real defect.
2. **DEC-12 (`f336801`) — a false-negative security check.** CHECK 3 asked the
   MODEL to read a secret; the model refused at the prompt layer and never
   invoked a tool, so `stage_file_gate` — the deterministic guard `files[]`
   actually flows through — was NEVER exercised. Fixed: CHECK 3 rewritten to
   drive `files[]` straight through the real gate, model-free, with a benign
   positive control; it now FAILS if the gate is removed. Principle logged: a
   security guard is verified by driving the guard directly, never by trusting
   model judgment.
3. **DEC-13 (`574287c`) — the GATE FINDING, closed.** Building the deterministic
   check surfaced that `stage_file_gate` matched on the RAW name, so a
   path-prefixed secret (`sub/.env`, `../.env`) slipped past. Fixed by ENFORCING
   the schema's "no directory" contract: any name with a path separator or a
   bare `..` is refused OUTRIGHT (explicit refusal over silent normalization),
   closing `/work` traversal at the root. Secret-name matching unchanged; a `..`
   inside a bare name (`archive..bak`) stays legal — no over-rejection.

**Sultan's Live SOP (2026-07-22, his hardware):** CHECK 1 (fibonacci → exit 0,
Arabic speech, budget cost) PASSED; CHECK 2 (traceback → self-correct within the
≤3 gate) PASSED; CHECK 3 (the gate deterministically blocked BOTH the direct
secret and the path-traversal secret, zero leaks) PASSED. **Personal sign-off
granted — the milestone is accepted.**

## 4. Security posture (the milestone's core outcome)

- **LOOK-only preserved:** the sandbox owns ZERO of the user's machine —
  execution happens EXCLUSIVELY inside the owned, throwaway container. The
  input-device bans (type/click/press/clipboard) stay absolute (DEC-6).
- **Isolation by construction:** `--network none --user 65534:65534 --read-only
  --tmpfs /work --cap-drop ALL --security-opt no-new-privileges` + memory/cpu/
  pids caps + `rm -f` always (DEC-3).
- **The staging guard is deterministic and proven:** secret-named files are
  refused BY NAME, path structure is refused by construction (DEC-13), binary is
  refused; content never enters a tool_result or a log line. Proven both by unit
  tests and by the deterministic live CHECK 3.
- **The kernel stays blind to Docker:** the ONLY kernel touch is a generic
  `on_interrupt` hook (DEC-3-C); the sealed kernel never names "docker".
- **The draw path is byte-untouched:** `highlight_gate.py`, `draw_dispatch.py`,
  the Option-A sync point, and the unified draw gate were git-verified unchanged
  throughout.

## 5. Final state

- **Tests:** 604 app + 27 sdk green; `muthis plugin test src/muthis_plugins/sandbox_exec` → ADMISSIBLE.
- **Line law:** every module ≤300 (`orchestrator.py` 299 — tracked debt; `file_reader.py` 208; `turn.py` 282).
- **main:** untouched at `637c687` — this branch has never been merged; that is Sultan's decision.
- **Catalog:** `tests/snapshots/look_tools_v2.json` byte-pins the 5-tool v2 catalog (`sandbox__run_code` added); the V1 four stay bare and byte-pinned to `look_tools_v1.json`.

## 6. What remains (Sultan's decisions / follow-ups — NOT actioned here)

1. **Merge `feature/v2-phase2-sandbox` → `main`** (Sultan runs it; consider tagging the milestone).
2. **DEC-7 — the Trust-Modes documentary sweep** is now UN-BLOCKED (its condition was "after the first Phase-2 milestone ships"); run it as its own standalone docs pass.
3. **DEC-1 — the AGENTS.md Key Files cleanup** is un-blocked (Phase 1 is merged); run it milestone-by-milestone under its constraint.
4. **Deferred deviations still OPEN** (`PROJECT_STATE.md`): (a) the spoken three-strikes eviction announcement — the ledger predicted it would land "with `sandbox_exec`", but this milestone did NOT wire it (no MCP eviction voice), so it REMAINS deferred; (b) `muthis/annotate` (intentionally unassigned); (c) the conformance-kit real-child boot check.
5. **The `web_research` milestone (Phase 2, M2)** inherits: the confirmation/taint path (DEC-2 / DEC-3-A / DEC-10), and MUST extract from `orchestrator.py` before touching it (the ceiling-debt constraint).

## 7. Commit ledger (this branch, `637c687..HEAD`)

```
574287c 2026-07-22 fix(sandbox_exec): reject path structure in staged names (DEC-13)
f336801 2026-07-22 test(sandbox_exec): prove the file-staging gate deterministically (DEC-12)
16afd45 2026-07-22 fix(tool_router): use "__" not "." for namespaced tool names (DEC-11)
2a2975d 2026-07-22 test(sandbox_exec): add diag_sandbox.py, the T6 live SOP diagnostic
d596115 2026-07-22 docs(decisions): log the orchestrator.py ceiling debt (tracked)
aee3608 2026-07-22 feat(sandbox_exec): wire run_code end-to-end + v2 catalog (T5, DEC-10)
d249447 2026-07-21 docs(decisions): record DEC-10, defer the confirmation path
24b8486 2026-07-21 docs(decisions): log the T5 scope finding (blocking)
ff52a3e 2026-07-21 feat(kernel): add the generic on_interrupt hook seam (T4, DEC-3-C)
183b597 2026-07-20 feat(sandbox_exec): add SandboxGate, the per-turn run limiter (T3)
dedfb15 2026-07-20 feat(sandbox_exec): add the container runner + DEC-9 stdin staging (T2)
3f14476 2026-07-20 docs(decisions): record DEC-9, staging via stdin bootstrap
023e869 2026-07-20 docs(decisions): log the T2 blocking finding under DEC-8
b72dac8 2026-07-20 feat(sandbox_exec): add the run_code contract + plugin skeleton (T1)
3db4888 2026-07-20 docs(decisions): record DEC-8, file staging path (Option B)
<this commit>  2026-07-22 docs(reports): Phase 2 M1 sandbox_exec closure report
```
