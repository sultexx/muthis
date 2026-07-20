# DECISIONS — Mut'his architectural decisions & logged ambiguities (the standing home: on ANY architectural ambiguity, record it here instead of guessing)

---

## DEC-1 (2026-07-19) — Key Files rows mix description with history — DEFERRED

- **Status:** DEFERRED — do NOT act on it before the Phase 1 merge.
- **Observation (root cause):** AGENTS.md Key Files rows mix file description with file history, which is the root cause of the repeated documentation drift (D1–D12).
- **Named examples (still-open drift, to be fixed BY this cleanup — NOT before the merge):**
  - `cloud/tool_schemas.py` row (~line 104): claims "~162" lines and describes the file as holding the LOOK-only schemas, but since Phase-0 M4 it is a ~43-line assembly re-export (the schemas live in `src/muthis_plugins/*/schema.py`) — contradicts the `muthis_plugins/` row (~line 127).
  - the "Planned next: geometric drawing Phase B — do not create until their build step" block (~lines 207–210): contradicts "Geometric drawing (Phase A + B-1 + B-2) is COMPLETE" (~line 438).
- **Proposed (post-Phase-1):** shorten each row to a concise description and migrate the detailed history to `docs/reports/`.
- **Constraint:** Execute the row-shortening milestone by milestone, not in one pass; re-run the full suite after each row — a wide edit to the source of truth must not itself introduce drift.
- **Why deferred:** it is a large edit to the source of truth and must not land before the Phase 1 merge.

---

## DEC-2 (2026-07-19) — Session-sticky taint — APPROVED

- **Item:** Taint (the untrusted-content protection flag) is SESSION-STICKY, not per-turn. The first untrusted
  content raises the protection level for the REST of the session; while tainted, high-impact tools require voice
  confirmation before they run.
- **Reason:** Once untrusted content (web / MCP / document results) has entered the context, the prompt-injection
  and exfiltration risk persists across turns — it does not end when the ingesting turn ends. A per-turn flag
  drops the guard too early; session-stickiness matches the threat's real lifetime.
- **Resolution:** One session-level taint state. Any untrusted content raises it; it stays raised for the rest of
  the session; every high-impact tool call made while tainted routes through the existing voice-confirmation
  seam. Per-message (fine-grained) taint tagging is OUT of scope — post-launch research. (The turn-level
  `ServiceOutcome.taint` / `TurnResult.taint` recorded since Phase 1 is the coarse precursor; this decision is the
  session-sticky escalation + enforcement.)
- **Implementation timing:** Enforcement lands with the `web_research` milestone — the first tool that ingests
  untrusted external content. Recorded now because `sandbox_exec` references the tainted-run confirmation path
  (DEC-3-A).

---

## DEC-3 (2026-07-19) — sandbox_exec boundaries — APPROVED

- **Item:** The architectural boundaries for the `sandbox_exec` milestone (V2 Roadmap §2, "الصندوق المعزول").
  Points A–E.
- **Reason:** The Roadmap approved the sandbox in principle (decisions #0 / #1 / #5, 2026-07-16) but left
  interpretive gaps — e.g. §2.5 says `SandboxGate` "mirrors `HighlightGate`" without saying decoupled-clone vs.
  shared-instance, and §2.3 / §2.8 imply but never spell out that network-less runs skip confirmation. These
  points pin those gaps and fix the decoupling / kernel-blindness absolutes that keep the sealed kernel free of
  Docker knowledge and protect the friction-less loop.
- **Resolution:**
  - **(A)** NO voice confirmation for isolated network-less runs — the friction-less loop is protected.
    Confirmation is reserved for network-enabled OR tainted-context runs (per DEC-2). (Roadmap §2.3:
    `--network none` default, network is a separate per-run-confirmed privilege; §2.8: tainted content →
    confirmation before an open-network run.)
  - **(B)** `SandboxGate` is FULLY DECOUPLED from `HighlightGate` — its own object built on the PATTERN, not the
    instance; it lives in the plugin / broker domain, NEVER in the sealed kernel. ("Mirror" in §2.5 = a decoupled
    clone, not a shared gate.)
  - **(C)** The kernel gains a GENERIC `on_interrupt` hook list and stays BLIND to Docker; the sandbox registers
    its `docker kill` there (Roadmap §2.6). F9 = silence + board clear + container death, one consistent
    behavior; the kernel never learns the word "Docker".
  - **(D)** A pre-packaged, fingerprint(sha256)-pinned image with a spoken first-pull (Roadmap §2.4).
  - **(E)** `/work/out` file-output retrieval is DEFERRED post-launch — stdout suffices for launch (Roadmap §2.4).
- **Implementation timing:** Lands with the `sandbox_exec` milestone (Phase 2, first infrastructure addition —
  not yet opened). (E) is post-launch.

---

## DEC-4 (2026-07-19) — doc_rag wrapping + injection threshold — APPROVED

- **Item:** For `doc_rag` (the visual-citation feature, «الاستشهاد المرئي»): where untrusted-content wrapping and
  taint-raising live, the injection threshold, and OCR honesty.
- **Reason:** Security a plugin author can weaken is not security. Centralizing the wrap + taint in the
  kernel / broker makes it an absolute every tool inherits; §3.2 delimiters + per-passage taint are the injection
  defense; a fixed env threshold keeps behavior predictable; honest OCR refusal preserves community credibility.
- **Resolution:** Wrapping and taint-raising live in the KERNEL / BROKER, NEVER in the plugin — a kernel-level
  security absolute that ALL tools inherit. §3.2 delimiters wrap every retrieved passage, and every retrieved
  passage raises taint (feeding DEC-2). The injection threshold is env-driven — `MUTHIS_DOC_INJECT_LIMIT=50000` —
  with NO auto-scaling. OCR is refused honestly (no silent low-confidence OCR).
- **Implementation timing:** Lands with the `doc_rag` milestone, inheriting the `web_research` defense (DEC-2).

---

## DEC-5 (2026-07-19) — muthis/capture during an active turn — APPROVED

- **Item:** How a plugin's `muthis/capture` bridge request is handled when it arrives while the kernel is
  mid-turn.
- **Reason:** The kernel's frame-capture chokepoint (hide → settle → capture) is turn-owned and load-bearing; a
  mid-turn bridge capture would race the overlay / draw lifecycle. Refusing politely (never raising) matches the
  `FileReader` / `tool_result` pattern.
- **Resolution:** A `muthis/capture` request received during an active turn is politely REFUSED with a short
  Arabic note; capture is served ONLY BETWEEN turns. A queue / concurrent-capture mechanism is OUT of scope —
  post-launch research.
- **Implementation timing:** Implemented with the FIRST real bridge consumer (the muthis-profile/1 capture bridge
  exists since Phase 1 but has no real consumer yet).

---

## DEC-6 (2026-07-20) — Trust Modes cancelled from the product vision — APPROVED

- **Item:** Trust Modes (the ASSIST / AUTOPILOT trust tiers that would grant real control over the user's mouse /
  keyboard / clipboard) are **cancelled from the product vision** — permanently removed, not deferred to a later
  phase.
- **Reason:** Sultan's decision, recorded at `plan_v6.md:27` (2026-07-14): the ACTION / click idea (Trust Modes)
  is **permanently removed from the product vision**. Mut'his's value is the LOOK-only teacher; owning the user's
  input devices is out of scope by **design, not by timing**. Formalized here so the canonical decision log — not
  only a V1-era plan file — carries it, since V2 governance already references it (AGENTS.md Self-Update rule #4,
  commit `323ee2a`).
- **Resolution:** The **input-device / machine-control boundary is PERMANENT and does not move at all** — there is
  no future "Trust Modes opening." The `type_text` / `press_hotkey` / `real_click` / `set_trust_mode` bans
  (AGENTS.md first "Do NOT" bullet) are absolute and final. This is DISTINCT from the sandbox-execution boundary,
  which moved once under DEC-3 / Roadmap #0 (in-container execution is not device control).
- **Implementation timing:** In force since 2026-07-14 (decision date); recorded canonically 2026-07-20. The
  documentary follow-through (purging the stale "designed / not in scope yet / until Trust Modes opens" wordings +
  the §12 Trust Modes section) is a separate DEFERRED cleanup — see DEC-7 — so logging DEC-6 does not itself
  trigger a doc sweep.

---

## DEC-7 (2026-07-20) — Trust Modes documentary sweep — DEFERRED

- **Status:** DEFERRED — do NOT execute before the first Phase-2 milestone (`sandbox_exec`) ships.
- **Item:** The full documentary cleanup that follows the DEC-6 cancellation: the stale "designed in
  ARCHITECTURE_v4_1.md §12 but **not in scope yet**" (AGENTS.md ~line 18-19), "LOOK-only is a hard boundary
  **until the Trust Modes phase is explicitly opened**" (AGENTS.md first "Do NOT" bullet, ~line 463), and the
  **§12 Trust Modes section itself in `ARCHITECTURE_v4_1.md`** (referenced from AGENTS.md:18). Also sweep sibling
  mentions — `MIGRATION_PLAN.md`, `LESSONS.md`, and the "future AUTOPILOT basis" framing around the frozen
  `reference/cursor_control.py`.
- **Reason:** Low-impact **stale wording about an already-cancelled feature**. The HARD contradiction it could
  cause was already resolved in AGENTS.md Self-Update rule #4 (`323ee2a`, which names DEC-6 / `plan_v6.md` as
  authority); what remains is imprecise phrasing, not a logical conflict. It is Sultan's own pre-existing deferred
  item (`plan_v6.md:361`). It does NOT block `sandbox_exec`, and doing it now (a multi-file sweep touching
  ARCHITECTURE_v4_1.md §12) would delay implementation for cosmetic gain.
- **Resolution / constraint:** Execute as a STANDALONE docs pass **AFTER** the first Phase-2 milestone lands —
  never before, never bundled into implementation work. When done: restate the AGENTS.md LOOK-only wordings as
  permanent (per DEC-6), retire or "cancelled — see DEC-6"-mark the §12 section, reconcile the sibling mentions,
  and settle the frozen `cursor_control.py`'s disposition. Re-run the full suite (532 + 27) after the sweep.
- **Implementation timing:** Post-first-Phase-2-milestone — a dedicated cleanup commit.

---

## DEC-8 (2026-07-20) — sandbox_exec file staging path — APPROVED

- **Item:** How model-provided `files[]` are delivered into the sandbox container given the DEC-3
  `--tmpfs /work` flag.
- **Reason:** P0 found LIVE that the Roadmap §2.2 ordering (`create → docker cp to /work → start`) does NOT
  deliver files under `--tmpfs /work` (§2.3): `/work` does not exist in the created container before start
  (`docker cp` fails with "destination must be a directory"), and the tmpfs would mask any pre-start write anyway
  (the container saw the staged file MISSING). A real §2.2-vs-§2.3 conflict, caught before writing T2.
- **Resolution:** Option (B), Sultan's sign-off. Input files are `docker cp`'d to a READ-ONLY path BEFORE start,
  preserving the `create → cp → start -a` sequence that runs the code directly (Roadmap §2.2 in spirit). `/work`
  stays the writable tmpfs scratchpad. Rationale: read-only inputs are inherently safer (code reads its sources,
  never mutates them); it keeps the container lifecycle simple (no split start/exec — a smaller error surface in
  our first execution tool); and "inputs read from a fixed path, `/work` is the scratchpad" is a cleaner mental
  model. Accepted trade-off: code that wants to MODIFY an input copies it into `/work` itself (covered by one line
  of the tool description).
- **Implementation timing:** Lands in T2 (the runner's staging step). Resolves the §2.2-vs-tmpfs tension P0
  surfaced.
- **T2 IMPLEMENTATION FINDING (2026-07-20) — BLOCKING, awaiting Sultan's re-ruling:** Building T2 revealed
  DEC-8 is NOT implementable as approved. Docker 29.6.1 REFUSES `docker cp` into ANY container created with the
  DEC-3 `--read-only` flag — verified twice, live — for BOTH the read-only rootfs AND the tmpfs `/work`, whether
  the container is merely created or already running: `Error response from daemon: container rootfs is marked
  read-only`. So `docker cp` staging (Roadmap §2.2) and `--read-only` (§2.3) are **mutually exclusive**; BOTH
  DEC-8 Option A (start→cp) and Option B (cp→start) are dead — they both depend on `docker cp`. The choice is now
  between two DEC-3-level directions, and only Sultan rules it:
  - **(1) KEEP `--read-only`, drop `docker cp`:** deliver files via a stdin bootstrap — a small fixed wrapper is
    the container command; `files[]` + code are framed on stdin; the wrapper writes them into the writable tmpfs
    `/work` and runs the code (cwd `/work`). Keeps ALL DEC-3 flags; no cp, no bind mount. Cost: more runner code
    (bootstrap + stdin framing, and a runtime present in the image); DEC-8's "read-only inputs" property becomes
    UNENFORCEABLE (the nobody code owns what it writes) — the FileReader secret/binary/size gates still apply at
    staging.
  - **(2) DROP `--read-only`, keep `docker cp`:** deliver files via `docker cp` exactly as Roadmap §2.2 states.
    Simple and cp-faithful. Cost: the rootfs is writable — but harmless in practice, since the container stays
    ephemeral (rm -f'd) + non-root (`--user 65534`) + `--network none` + `--cap-drop ALL` + `--security-opt
    no-new-privileges` + memory/cpu/pids-capped, so a writable rootfs only affects the doomed container. A DEC-3
    revision.
  - T2 is STOPPED until this is ruled — no runner code written; the finding was proven by scratchpad probes only.
