# DECISIONS — Mut'his architectural decisions & logged ambiguities (the standing home: on ANY architectural ambiguity, record it here instead of guessing)

---

## DEC-1 (2026-07-19) — Key Files rows mix description with history — DEFERRED

- **Status:** DEFERRED — do NOT act on it before the Phase 1 merge.
- **Observation (root cause):** AGENTS.md Key Files rows mix file description with file history, which is the root cause of the repeated documentation drift (D1–D12).
- **Proposed (post-Phase-1):** shorten each row to a concise description and migrate the detailed history to `docs/reports/`.
- **Why deferred:** it is a large edit to the source of truth and must not land before the Phase 1 merge.
