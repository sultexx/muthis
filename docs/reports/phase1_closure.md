# Phase 1 — Closure Report (Broker, Privileges & MCP Bridge)

- **Project:** Mut'his V2
- **Branch:** `feature/v2-phase1-broker-mcp`
- **Status:** CLOSED pending Sultan's merge (the merge is his to run; not performed here)
- **Written:** 2026-07-19 (English, all-ASCII UTF-8 -- committed to git, cannot byte-reverse)
- **Companion:** `docs/reports/phase1.md` (the milestone-detail report; this is the closure/audit record)

> This report certifies that Phase 1 closed correctly: the work is complete, the
> documentation is consistent (except two drifts explicitly deferred under
> DEC-1), the live exit gate passed, and the tree is in a clean, mergeable state.

---

## 1. Verdict

Phase 1 (the Capability Broker, the privilege model, and the MCP bridge) is
COMPLETE and documentation-clean. The only remaining AGENTS.md drift is two
pre-V2 items, both named and deferred under `DECISIONS.md` DEC-1 for the
post-merge cleanup. Phase 1 is held at its gate awaiting Sultan's merge. No
Phase 2 code exists.

## 2. Implementation -- M1-0 -> M1-7 complete

Detail lives in `docs/reports/phase1.md`. Milestone commits:

| Milestone | Commit | Summary |
|---|---|---|
| M1-0 governance | `08b6929` (merge to main) + tag `pre-v2-phase1` + `d56122d` | Phase 0 merged to main; anchor tagged; branch cut; snapshot-eol defect fixed |
| M1-1 | `7e9863b` | Q-4 settled: 8 compat shims removed; consumers flipped to `muthis.kernel.*` |
| M1-2 | `abe07f8` | FrameCapture extracted (orchestrator 300 -> 284); the ONE `router` seam |
| M1-3 | `8247e83` | per-plugin budget column; sovereignty rule; V1 budget contract untouched |
| M1-4 | `1535e22` | broker (grants sha256-pinned, gated context, trust flow); kit violation suite LIVE |
| M1-5 | `62df0df` | the MCP layer (stdlib client/host/policy/proxy; kernel stays blind); taint live |
| M1-6 | `080a521` | out-of-process runtime; muthis-profile/1 bridge; `examples/hello_world` |
| M1-7 | `5fb5a15` + `8392061` | root composition; `examples/demo_server`; two live-gate diags; docs |

## 3. Documentation consistency -- three rounds

The source of truth (`AGENTS.md`) was hardened over three audit rounds. Every
finding is now either fixed or deferred under DEC-1.

| Round | Findings | Reported | Fixed in |
|---|---|---|---|
| 1 | D1-D10 (Key Files table drift: deleted-shims row, false 300 ceiling, stale counts, missing taint clauses, undocumented `.gitattributes`) | `phase1.md` section 10 (`d803738`) | `50a57bf` |
| 2 | D11 (a miss in the round-1 audit: stale shim-identity test claim) + D12 (Architecture prose "are compat shims" contradicting "Shims removed") | prior-turn report | `1d208b8` |
| 3 | Exhaustive end-to-end prose+table audit: confirmed D11/D12 + 3 more M1-era sites (draw_dispatch "orchestrator at 300 ceiling"; main.py ~204->256 + missing broker/MCP composition; `_capture_downscaled` -> `FrameCapture.capture`); found 2 pre-V2 out-of-scope drifts | this closure record + DEC-1 | `1d208b8` (M1 sites); 2 out-of-scope -> DEC-1 |

Governance scaffolding that supported the rounds: `b2d25a1` (DEFERRED/DEVIATIONS
ledger), `d1ac90f` (annotate deferral hardened), `59461f3` (DECISIONS.md
created), `af556af` (phase1.md section-10 closure note, body kept immutable),
`20f4448` (DEC-1 logged), `84a4808` (DEC-1 named examples + milestone-by-
milestone constraint), `0b1068a` (the initial sdk-row correction that triggered
round 1).

## 4. Live exit-gate results

Both zero-provider-cost gate diagnostics PASSED in engineering smoke (recorded
in `phase1.md` section 4); Sultan reviewed and closed Phase 1.

- `scripts/diag_hello_plugin.py`: PASS -- the reference community plugin served out-of-process end to end (trust -> mount -> namespaced router catalog -> Arabic greeting through a real child, wrapped + tainted, budget-attributed).
- `scripts/diag_mcp_mount.py`: PASS -- a real foreign-implementation MCP server mounted live; its destructive DECOY tool HIDDEN by the look-and-advise filter; read-only tools answered wrapped as untrusted data + tainted; an ungranted mount refused live.
- V1 regression: the app suite (532) preserves the 474-test V1 oracle unchanged; the byte-pinned model-visible catalog is unaltered.

## 5. Deferred cleanup -- DECISIONS.md DEC-1

Root cause of the repeated documentation drift, deferred to post-merge:

- **Observation:** AGENTS.md Key Files rows mix file description with file history.
- **Named examples (still-open, out of the M1-0->M1-7 fix scope):**
  1. `cloud/tool_schemas.py` row (~line 104): "~162" vs actual 43; describes the file as holding the schemas, but it is a ~43-line assembly re-export since Phase-0 M4 -- contradicts the `muthis_plugins/` row (~127).
  2. the "Planned next: geometric drawing Phase B -- do not create" block (~lines 207-210): contradicts "Geometric drawing (Phase A + B-1 + B-2) is COMPLETE" (~line 438).
- **Proposed:** shorten each row to a concise description; migrate detailed history to `docs/reports/`.
- **Constraint:** execute milestone by milestone, re-running the full suite after each row, so the wide source-of-truth edit cannot itself introduce drift.
- **Status:** DEFERRED -- must not land before the Phase 1 merge.

## 6. Final state

- **Tests:** 532 app + 27 sdk green (docs-only changes this closure; no code touched).
- **main:** untouched at `08b6929` (the Phase-0 merge) -- the Phase 1 branch has never been merged; that is Sultan's decision.
- **Working tree:** clean.
- **Scope discipline:** no Phase 2 code exists (not even a stub); the DEC-1 cleanup was NOT performed (post-merge).

## 7. What remains (Sultan's decisions, not actioned here)

1. Merge `feature/v2-phase1-broker-mcp` into `main` (Sultan runs it).
2. Post-merge: execute the DEC-1 Key Files cleanup under its constraint.
3. Open Phase 2 explicitly (not before then).

## 8. Commit ledger (this branch, `pre-v2-phase1..HEAD`)

```
d56122d 2026-07-17 fix(tests): pin snapshot bytes (M1-0 defect)
7e9863b 2026-07-17 refactor(kernel): settle Q-4 -- remove 8 shims (M1-1)
abe07f8 2026-07-17 refactor(kernel): M1-2 FrameCapture + router seam
8247e83 2026-07-17 feat(kernel): M1-3 per-plugin budget column
1535e22 2026-07-17 feat(broker): M1-4 grants/broker/trust; kit LIVE
62df0df 2026-07-17 feat(mcp): M1-5 the MCP layer
080a521 2026-07-17 feat(sdk,mcp): M1-6 runtime + profile bridge
5fb5a15 2026-07-17 feat(main,diag): M1-7 root composition + diags
8392061 2026-07-17 docs(phase1): AGENTS/PROJECT_STATE/CONTRIBUTING
0b1068a 2026-07-18 docs(agents): correct the sdk row (round-1 trigger)
b2d25a1 2026-07-18 docs(project-state): DEFERRED/DEVIATIONS ledger
d803738 2026-07-18 docs(reports): phase1.md milestone report + convention
50a57bf 2026-07-18 docs(agents): close D1-D10 (round 1)
d1ac90f 2026-07-18 docs(project-state): annotate phase intentionally unassigned
59461f3 2026-07-18 docs: add DECISIONS.md
1d208b8 2026-07-19 docs(agents): close D11+D12 + exhaustive audit (rounds 2-3)
af556af 2026-07-19 docs(reports): phase1.md section-10 closure note
20f4448 2026-07-19 docs(decisions): log DEC-1
84a4808 2026-07-19 docs(decisions): DEC-1 named examples + constraint
<this commit>  2026-07-19 docs(reports): Phase 1 closure report
```
