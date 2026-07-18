# Phase 1 — Broker, Privileges & MCP Bridge — Milestone Report

- **Project:** Mut'his V2
- **Branch:** `feature/v2-phase1-broker-mcp`
- **Phase status:** CODE-COMPLETE; live exit gate pending Sultan's run + explicit authorization
- **Written:** 2026-07-18 (English UTF-8 — committed to git; never an external paste/PDF, so the bytes can't reverse)
- **Source of truth:** `AGENTS.md` (this report is a point-in-time record, not authority)

> Note on the report's own commit hash: a report cannot contain the hash of the
> commit that adds it (chicken-and-egg). This report is introduced by the Task-3
> governance commit on `feature/v2-phase1-broker-mcp`; the milestone commit
> hashes it documents are in §12.

---

## 1. Status & Gate Posture

Phase 1 (the Capability Broker, the privilege model, and the MCP bridge) is
code-complete on `feature/v2-phase1-broker-mcp`. It is **NOT merged to `main`**
(main still carries the latent autocrlf snapshot bug until the merge lands — see
§9). No Phase 2 code exists. The phase is held at its exit gate awaiting
Sultan's live run of the two zero-cost diagnostics plus a V1 regression diag,
and his explicit authorization to merge.

## 2. Milestones & Commits

| Milestone | Commit | Summary |
|---|---|---|
| M1-0 governance | `08b6929` (merge to main) + tag `pre-v2-phase1` + `d56122d` | Phase 0 merged to `main`; rollback anchor tagged; branch cut; the snapshot-eol defect fixed |
| M1-1 | `7e9863b` | Q-4 settled: 8 compat shims removed; every consumer flipped to `muthis.kernel.*` |
| M1-2 | `abe07f8` | `FrameCapture` extracted (orchestrator 300 → 284); the ONE `router` seam injected; root composition |
| M1-3 | `8247e83` | per-plugin budget column (`plugins` ledger key); sovereignty rule; V1 budget contract untouched |
| M1-4 | `1535e22` | `broker/` (grants sha256-pinned, gated context, trust flow); conformance violation suite goes LIVE |
| M1-5 | `62df0df` | the MCP layer (stdlib client/host/policy/proxy; kernel stays blind); taint metadata live |
| M1-6 | `080a521` | `mcp_runtime` out-of-process serving; muthis-profile/1 bridge; `examples/hello_world` |
| M1-7 | `5fb5a15` + `8392061` | root composition (broker+host+router); `examples/demo_server`; two live-gate diags; docs |

Post-close governance commits: `0b1068a` (AGENTS sdk-row correction), `b2d25a1`
(DEFERRED/DEVIATIONS ledger), and the commit adding this report.

## 3. Files Changed (`pre-v2-phase1..HEAD`, milestone work)

36 added, 8 deleted, 47 modified.

**Created (architecture):**
- Broker: `src/muthis/broker/{__init__,grants,broker,trust}.py`
- MCP host: `src/muthis/broker/mcp/{__init__,client,host,policy,proxy_plugin}.py`
- Kernel: `src/muthis/kernel/frame_capture.py`
- SDK MCP: `sdk/muthis_sdk/mcp/{__init__,framing,messages}.py`, `sdk/muthis_sdk/mcp_runtime.py`
- Examples: `examples/hello_world/{__init__.py,muthis-plugin.toml,plugin.py}`, `examples/demo_server/server.py`
- Registrations: `plugins.d/{README.md,demo_server.toml.sample,hello_world.toml.sample}`
- Diags: `scripts/{diag_hello_plugin,diag_mcp_mount}.py`
- Tests: `tests/{fake_mcp_server,fixture_bridge_plugin,test_broker,test_budget_plugins,test_frame_capture,test_grants,test_mcp_bridge,test_mcp_client,test_mcp_host,test_mcp_policy}.py`, `sdk/tests/{test_mcp_framing,test_mcp_runtime}.py`
- Infra: `.gitattributes` (pins the byte-snapshot against eol conversion)

**Deleted:** the 8 compat shims — `src/muthis/{budget,draw_dispatch,highlight_gate,history_hygiene,orchestrator,turn,turn_pass,verbosity}.py` (Q-4).

**Modified:** kernel `{budget,orchestrator,tool_router,turn,turn_pass}.py`, `main.py`,
`overlay_autohide.py`, `speech_stream.py`, `stubs.py`, `vision/downscale.py`,
`voice_out.py`; SDK `{__init__,context,manifest,pyproject}` + `conformance/{checks,runner}` + `tests/test_conformance`;
docs `AGENTS.md`, `PROJECT_STATE.md`, `CONTRIBUTING.md`, `.gitignore`; and ~25
script/test files. **Of the ~25 script/test modifications, all but two
(`test_kernel_layering`, `test_conformance`) are the mechanical M1-1 import
flip (`muthis.X` → `muthis.kernel.X`) — no test logic changed**, which is how
the 474-test V1 oracle was preserved.

## 4. Tests Executed

- App suite: **532 passed** (`set PYTHONPATH=src && python -m pytest tests/ -q`). The 474 V1-oracle tests are content-unchanged.
- SDK suite: **27 passed** (`python -m pytest sdk/tests -q`, editable install).
- New guards: `test_grants`, `test_broker`, `test_budget_plugins`, `test_frame_capture`, `test_mcp_client`, `test_mcp_policy`, `test_mcp_host`, `test_mcp_bridge` (app) + `test_mcp_framing`, `test_mcp_runtime` (SDK). MCP tests run against REAL child processes and an INDEPENDENT sync fake server (protocol cross-validation, not self-validation).
- Live-gate diagnostics (engineering smoke, **zero provider cost**, both PASS): `scripts/diag_hello_plugin.py` (community plugin served out-of-process end to end), `scripts/diag_mcp_mount.py` (a real foreign server mounted; its destructive decoy tool hidden by the filter; results wrapped + tainted; ungranted mount refused).
- Full-composition idle boot: OK.
- Conformance kit on the four core plugins: 4x ADMISSIBLE, 0 SKIPs.

## 5. Documentation Updates

- `AGENTS.md`: Key Files rows for `frame_capture`, `broker/`, `broker/mcp/`, `sdk mcp`, examples/plugins.d, Phase-1 tests; the budget-column note; a Phase-1 architecture bullet; Build & Run (trust flow + diags); Do NOT (broker/MCP boundary); the corrected sdk row (commit `0b1068a`); the reports convention (this commit).
- `PROJECT_STATE.md`: Phase-1 lead section; the DEFERRED/DEVIATIONS ledger (commit `b2d25a1`).
- `CONTRIBUTING.md`: out-of-process quickstart + the LIVE violation suite as the admission bar.
- `docs/reports/phase1.md`: this report.

## 6. Architectural Decisions (as applied)

- **Q-1.0..Q-1.4 honored:** Phase 0 merged + tagged before Phase 1; MCP implemented in Python stdlib (SDK zero-dependency law intact); the profile scope is `read_file` + `capture` + negotiation only (annotate deferred); grants via `python -m muthis.broker.trust`; a self-contained Python demo server (no Node/npx) for the live gate.
- **Draw path stays sacred (ruling C-1):** neither the broker nor the MCP layer touches `draw_dispatch` / `highlight_gate` / the overlay draw circuit; the router services perception/execution tools only.
- **Taint is recorded, not enforced (this phase):** external (MCP) results raise `ServiceOutcome.taint` and a coarse turn-level `TurnResult.taint`; enforcement (flipping high-impact tools to confirm-first) ships with the Phase-2 tools that would be gated.
- **Phase-1 scope law:** trusted MCP tools mount into the kernel `ToolRouter` but are NOT offered to the model — the model-visible catalog stays the byte-pinned V1 four until Phase 2's designed merge.
- **The kernel stays blind to MCP (§8.1):** all MCP knowledge lives under `broker/mcp/`; server tools reach the kernel as ordinary `ToolDescriptor`s.
- **Grant = manifest-hash consent:** any manifest byte change invalidates the grant by construction (the update-diff rule), no diff UI required.
- **Sync stdio for the out-of-process runtime:** the Windows asyncio-stdin pipe swamp is avoided by design; the runtime owns its wire encoding.

## 7. Deferred Items

Tracked in the gate-audited `PROJECT_STATE.md` > `DEFERRED / DEVIATIONS` ledger:
(a) spoken three-strikes eviction announcement → Phase 2; (b) the
`muthis/annotate` profile bridge (Q-1.2) → **phase UNASSIGNED, needs Sultan's
assignment**; (c) the conformance-kit real-child boot check → Phase 2. See the
ledger for each item's reason and closing condition.

## 8. Known Limitations

- Taint is coarse (turn-level, record-only) — deliberate per roadmap §3.2; not yet an enforcement gate.
- `muthis/annotate` is absent — external plugins cannot draw this phase.
- The conformance kit does not spawn `kind=mcp` children (covered instead by the runtime tests).
- Per-plugin budget costs are all `None` in Phase 1 — the column is live plumbing over inert money (no paid plugin exists yet).
- MCP results are text-only; image/audio blocks are dropped with an Arabic note (a visual-injection channel deferred by design).
- The three-strikes eviction announcement is logged, not spoken (deferral (a)).
- Region-level, not pixel-level, coordinate accuracy remains a standing V1 honesty limit (unchanged by Phase 1).

## 9. Live-Critical Defects Found & Fixed During Phase 1

The test suite and live diags caught four real defects (not speculative — each root cause was confidently identified before the fix):

1. **Snapshot eol (`d56122d`):** the M1-0 merge let `core.autocrlf` smudge the byte-pinned `look_tools_v1.json` LF→CRLF, failing the zero-behavior guard on Windows checkouts (schemas never drifted). Fix: `.gitattributes` scoping `tests/snapshots/**` as `-text` + original LF bytes restored. Main carries this latent bug until the phase merge.
2. **Subpackage import miss (`7e9863b`):** the first shim-consumer inventory missed `src/muthis/vision/downscale.py` (a `..turn` import). Caught by the milestone test gate; fixed in the same milestone.
3. **EOF strike delay (`62df0df`):** a dead MCP server left in-flight requests to wait out the full 20s timeout (3 strikes = 60s). Fix: EOF now fails pending requests instantly, so a dead server strikes immediately.
4. **cp1256 wire (`080a521`):** Windows pipes default to the locale codepage, breaking the strict-UTF-8 MCP wire at the first Arabic byte (0xC8). Fix: the runtime reconfigures utf-8, the client armors python children (`PYTHONUTF8`/`PYTHONIOENCODING`), and the fake foreign server declares utf-8.

## 10. Close-Out Documentation Audit (REPORTED, not resolved — awaiting approval)

Per the Task-1 instruction and the architectural-discrepancy governance rule,
the full Key Files table was audited for M1-0..M1-7 drift. The sdk row was
corrected (authorized); the following are **reported for Sultan's approval,
NOT silently resolved.** All are documentation drift (code is correct; docs are
stale) — none is a code-vs-architecture discrepancy.

| # | Sev | Location | Drift | Suggested fix (pending approval) |
|---|---|---|---|---|
| D1 | HIGH | AGENTS Key Files: "the 8 compat shims" row | Documents 8 files DELETED in M1-1 (`7e9863b`) as still present | Rewrite for `kernel/__init__.py` only; note shims removed, guard test enforces |
| D2 | MED | orchestrator.py row | "300 (AT the ceiling — any addition must extract first)" — actual 284 after M1-2; the "AT the ceiling" guardrail is now false (16 lines headroom); omits M1-2 | Update count to 284; note FrameCapture extraction + the `router` seam |
| D3 | LOW | budget.py row | "~229" — actual 267 | Refresh count |
| D4 | LOW | turn_pass.py row | "~195" — actual 205; a duplicated clause ("extracted whole from orchestrator._consume_stream" x2); omits M1-5 taint recording | Refresh count; de-dup; note taint |
| D5 | LOW | turn.py row | "~255" — actual 260; omits the M1-5 `TurnResult.taint` field | Refresh count; note taint field |
| D6 | LOW | tool_router.py row | "~192" — actual 219; tagged Phase 0 only; omits M1-3 `plugin_ledger` seam + M1-5 route taint | Refresh count; add Phase-1 note |
| D7 | LOW | broker/ row | "~95-140 each" — actual 85-144 (grants 144 exceeds 140) | Widen range to ~85-145 |
| D8 | LOW | broker/mcp/ row | "~130-266" — actual 47-266 (proxy 47, policy 126) | Correct low end to ~47 |
| D9 | LOW | sdk mcp row | "~65-229" — actual 46-229 (mcp/__init__ 46) | Correct low end to ~46 |
| D10 | INFO | (missing) | `.gitattributes` (load-bearing: pins the byte-snapshot) is undocumented | Add a note near the snapshot/tests discussion |

Recommendation: authorize a single follow-up docs commit to close D1-D10 (D1 and
D2 are the material ones — a deleted-files row and a false ceiling guardrail).

## 11. Acceptance Criteria Status (Phase-1 plan §8)

| Criterion | Status |
|---|---|
| Roadmap exit gate: a community hello-world plugin works out-of-process | PASS (engineering smoke; awaiting Sultan's live confirmation) |
| Roadmap exit gate: a real MCP server mounted live, read-only filter enforced | PASS (engineering smoke; awaiting Sultan's live confirmation) |
| All suites green (474 oracle preserved + guards + SDK) | PASS — 532 app + 27 SDK |
| Privileges enforced: ungranted capability refused; hash change invalidates; quarantine; three strikes | PASS (tested + live) |
| Conformance kit: 0 SKIPs; violating fixtures rejected | PASS |
| Taint recorded per external result; V1 draw/audio paths byte-unchanged | PASS |
| Draw path untouched; every file <= 300; docs updated | PASS (max touched file 284) |

## 12. Commit Ledger

```
08b6929  Merge Phase 0 to main            (M1-0; tag pre-v2-phase1 here)
d56122d  fix(tests): pin snapshot bytes   (M1-0 defect fix)
7e9863b  refactor(kernel): settle Q-4     (M1-1)
abe07f8  refactor(kernel): M1-2 surgery   (M1-2)
8247e83  feat(kernel): M1-3 budget column (M1-3)
1535e22  feat(broker): M1-4 grants/broker (M1-4)
62df0df  feat(mcp): M1-5 the MCP layer    (M1-5)
080a521  feat(sdk,mcp): M1-6 runtime      (M1-6)
5fb5a15  feat(main,diag): M1-7 composition(M1-7)
8392061  docs(phase1): M1-7 docs          (M1-7)
0b1068a  docs(agents): sdk row correction (post-close Task 1)
b2d25a1  docs(project-state): deviations  (post-close Task 2)
```
