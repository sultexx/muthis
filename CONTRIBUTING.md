# Contributing to Mut'his (مطحس)

> Skeleton born in V2 Phase 0 (constitution §1.4, decision Q-5). It grows into
> the full community guide at Phase 4 (the launch kit); the LAWS below are
> already binding for every contribution, human or agent.

## The non-negotiable laws (acceptance conditions)

1. **≤ 300 lines per module, single responsibility, importable in isolation.**
   A module nearing the ceiling is SPLIT, never compressed. PRs that push a
   file past 300 lines are rejected regardless of merit — extract first.
2. **The golden rule — "look and advise only", enforced by construction.**
   No `input.mouse`, `input.keyboard`, or `clipboard.write` exists anywhere:
   not in the muthis-sdk capability enum, not in tool schemas, not as stubs.
   Execution is allowed EXCLUSIVELY inside the Mut'his-owned sandbox
   (arrives in Phase 2 behind the `sandbox.execute` capability).
3. **Language split.** User-facing strings (speech, captions, tool_result
   notes) are Arabic — Arabic is the reference language, not a translation.
   Logs, comments, identifiers, and commit messages are English. The two
   never mix in one surface.
4. **Wrappers and plugins own no lifecycles** (V1 Law 11, extended by the
   plugin contract): no loops, no locks, no retries, no conversation memory
   outside the kernel. Plugin failures RETURN as short Arabic notes in a
   ToolResult — they never raise into the kernel.
5. **Live-test SOP.** Every audio/UI-touching change ends with a live
   `scripts/diag_*.py` run and human approval before its commit lands. Unit
   tests alone have missed real bugs here (Tcl teardown, caption pacing) —
   the culture is the fix.
6. **Privacy first.** No transcripts, audio, or screenshots are written to
   disk by default; working memory lives in RAM and dies with the session.

## Plugins (the V2 surface)

- A plugin = `muthis-plugin.toml` + a `ToolPlugin` subclass over `muthis-sdk`
  (see `src/muthis_plugins/` — the four core tools are the reference
  consumers, and `sdk/tests` shows the contract under test).
- Capabilities come from the CLOSED enum only; an unknown capability fails
  manifest load. Community plugins are `kind = "mcp"` (out-of-process,
  Phase 1+); `kind = "native"` is reserved for signed core plugins.
- **Registry admission bar:** `muthis plugin test <your-plugin-dir>` must
  print ADMISSIBLE (exit 0). The permission-violation suite joins the kit
  with the Phase-1 broker.

## Workflow

- Branches: `feature/<description>` or `fix/<description>`.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`),
  imperative mood, English, explain the WHY. Never force-push `main`.
- Tests: `set PYTHONPATH=src && python -m pytest tests/ -q` (app) and
  `python -m pytest sdk/tests -q` (SDK). Both suites green is the floor;
  behavior-affecting changes add tests.
- Read `AGENTS.md` first — it is the single source of truth; this file only
  carries the acceptance conditions.
