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
  - **→ RESOLVED by DEC-9** (2026-07-20): keep `--read-only`, deliver via a stdin bootstrap; supersedes the
    `docker cp` staging mechanism entirely.

---

## DEC-9 (2026-07-20) — sandbox_exec file staging via a stdin bootstrap — APPROVED (supersedes DEC-8's mechanism)

- **Item:** How model-provided `files[]` + the user `code` are delivered into the sandbox container, now that
  `docker cp` is proven incompatible with the DEC-3 `--read-only` flag (see the DEC-8 finding above).
- **Reason:** All three worked-around options sacrificed something (drop `--read-only`, or rebuild an image per
  run breaking the ~0.5 s warm cycle). A fourth path sacrifices NOTHING: it keeps every DEC-3 flag AND avoids
  `docker cp` at the root rather than working around it.
- **Resolution:** Sultan's sign-off. **Keep `--read-only`** (defence in depth — the code cannot write system
  libraries or plant files in exec paths). The `--tmpfs /work:rw` is the ONLY writable region (already DEC-3).
  Input files and the user code are passed **via stdin** to a tiny fixed **bootstrap** that is the container
  command; it writes them into the writable `/work` and executes from `cwd=/work`. **NO `docker cp` anywhere;**
  no bind mounts; no host env. The sequence stays `create → start -a` (start runs the bootstrap, which stages
  then execs) — no split lifecycle. File contents cross the stdin wire **base64-encoded** (`files[]` is ≤ 1 MB
  per §2.4, so the overhead is trivial). This SUPERSEDES DEC-8's read-only-cp staging path while fully preserving
  DEC-8's intent (inputs reach the container, code runs directly) by a safer mechanism. Verified live before
  implementation — the bootstrap writes `/work` under `--read-only`, and `--workdir /work` must NOT be used (it
  makes Docker pre-create `/work` root-owned `0755`, blocking the `nobody` user; cwd is set by the bootstrap's
  own subprocess instead).
- **Implementation timing:** T2 (`runner.py` + `bootstrap.py`). FileReader gates (secret-name / binary) apply to
  each file before base64 encoding; the §2.1 total-size cap (1 MB) is enforced in the runner.

---

## T5 SCOPE FINDING (2026-07-21) — BLOCKING, awaiting Sultan's ruling

Investigating T5 against the real code shows its stated shape — "wire into the `ToolRouter` in `main.py`" +
"route through the **EXISTING** high-impact voice-confirmation seam" — does not match reality. Four concrete
gaps, none guessable:

1. **`run_code` is refused, not serviced — a KERNEL change is required.** `turn_pass.consume()` detects only the
   draw tools, `request_screen_refresh`, and `read_local_file`; EVERY other tool falls to the `else` branch and
   is logged + dropped as a "LOOK-only violation" (`turn_pass.py:155-160`). So `sandbox.run_code` would be
   refused. Servicing it needs a NEW branch in `turn_pass.py` (route through `router.service`, like the read at
   194-196) + result-pairing in `turn.py`'s `build_tool_result_message` + the agentic loop continuing on it —
   ≥2 kernel modules, NOT main.py wiring, and it re-opens "T4 is the ONE kernel touch."
2. **The confirmation seam does NOT exist.** No `trust/` package; `claude_agent.py:9` / `tool_schemas.py:16`
   reference an intended `trust/confirm_gate.py`, and `turn_pass.py:199` / `turn.py:143-144` / `policy.py:8-9` /
   `main.py:140` all say confirm-first enforcement "arrives with Phase 2's first high-impact tool." So "EXISTING"
   is inaccurate — it must be BUILT, and "confirmation" is undefined: a BLOCKING user yes/no voice round-trip
   (record → STT → parse), or the existing one-way spoken ack?
3. **`TurnResult.taint` is TURN-level, not the session-sticky flag DEC-2 describes** (`turn.py:141-145`), and
   there is NO mechanism to reset a per-turn `SandboxGate` — the kernel is blind to the sandbox and T4 was the
   only kernel touch, so nothing resets the gate at turn start without another kernel seam.
4. **The `docker kill` hook cannot learn the active container name.** T4's hook fires a generic `Callable`; the
   kill must target `muthis-run-<uuid>`, but the runner does not expose its active container yet (a seam needed).

Also note: in THIS milestone confirmation is essentially never triggered — the launch schema has NO network
param (so no network-enabled run), and taint is only populated later by `web_research`; the plan itself calls
DEC-2 enforcement here "PARTIAL / dead code."

**STOPPED — no T5 code written. Sultan to rule on:** (a) the additional KERNEL touches (turn_pass run_code
routing + `turn.py` pairing; a generic turn-start reset hook for the gate) — authorize or re-architect;
(b) what "confirmation" IS (build a blocking voice yes/no gate; OR wire only the confirmation DECISION behind an
injectable seam and DEFER the voice round-trip, since it is unexercised this milestone; OR reuse the one-way
ack); (c) whether to SPLIT T5 (T5a mount + servicing + snapshot + kill-hook; T5b the confirmation gate).

---

## DEC-10 (2026-07-21) — high-impact confirmation path deferred to web_research — APPROVED

- **Item:** WHEN the high-impact voice-confirmation path (DEC-3-A) is built, given the T5 finding that it does
  not exist and has no trigger this milestone.
- **Reason:** Proven live that confirmation has NO trigger in the sandbox_exec milestone — the launch schema has
  no network param (so no network-enabled run per DEC-3-A), and taint is unpopulated until `web_research`.
  Building the confirmation seam now violates stub-first ("do not build before the need") and would be dead code
  with no consumer; its actual shape (blocking voice yes/no vs. the one-way ack) is only knowable at its first
  real consumer.
- **Resolution:** Sultan's sign-off. **DEFER the entire high-impact voice-confirmation path to the
  `web_research` milestone** — its first real consumer (network access + populated session taint), where its
  shape is knowable. This corrects the original T5 brief's false premise ("route through the EXISTING seam") and
  preserves DEC-3-A's intent (confirmation for network / tainted runs) by binding the mechanism to its consumer.
  T5's scope is corrected to **core wiring only**: the turn_pass service branch, the `turn.py` result pairing,
  the `docker kill` on_interrupt registration, and the byte-pinned v2 catalog snapshot — NO confirmation, NO
  network-param plumbing, NO web-taint plumbing (all deferred).
- **Implementation timing:** The confirmation mechanism lands WITH `web_research`. T5 (this milestone) ships
  without it. A network-less untainted run — the only kind possible now — runs directly with no confirmation.

---

## CONSTRAINT (2026-07-22) — orchestrator.py ceiling debt — TRACKED

- **Item:** `orchestrator.py` sits at **299/300** lines after T5 (the sandbox seam threading) — a ONE-line margin.
- **Reason:** The ≤300-line law now leaves no room. An edit that adds even a single line without extracting first
  would blow the ceiling mid-implementation — the exact surprise the "extract, don't compress" law (§17.4)
  exists to prevent.
- **Resolution / constraint:** ANY future touch to `orchestrator.py` — notably **web_research (Phase-2
  Milestone 2)** — MUST **extract before adding**, NEVER compress. Identify the extraction candidate at PLANNING
  time, not mid-implementation. (A likely candidate: the `run_turn` `finally` teardown — the whiteboard-undim +
  auto-hide arm — could move to a small `turn_teardown.py`, mirroring the frame_capture / voice_out extractions.)
- **Implementation timing:** No action now (299 is legal). A planning-time flag for the next
  orchestrator-touching milestone.

---

## DEC-11 (2026-07-22) — namespaced plugin tools use "__" not "." — APPROVED (amends ruling C-3)

- **Item:** The separator between a plugin's namespace and its tool name in the model-visible catalog.
- **Reason:** The T6 LIVE SOP hit a HARD Anthropic API rejection on CHECK 1: `tools.4.custom.name: String should
  match pattern '^[a-zA-Z0-9_-]{1,128}$'` (request_id req_011CdGm91DEbN9Y9GRZxsLwa). Ruling C-3's dot-namespacing
  (`sandbox.run_code`) is INCOMPATIBLE with that pattern — the dot is not permitted. `sandbox.run_code` was the
  FIRST namespaced tool ever exposed to the model (the V1 four use bare names under C-3's core-name exemption),
  so the incompatibility was latent in the architecture until a live run surfaced it — a correctness failure,
  not cosmetic, caught by a real 400 and not by theory.
- **Resolution:** Sultan's sign-off. Namespaced plugin tools are **`<namespace>__<tool>`** (DOUBLE underscore) —
  e.g. `sandbox__run_code`. A double underscore satisfies the API pattern AND (unlike a single `_`) keeps the
  namespace boundary UNAMBIGUOUS and programmatically reversible (a single `_` is indistinguishable from an
  underscore inside a tool name, breaking router namespace parsing). This AMENDS ruling C-3's separator for ALL
  namespaced plugin tools — present and future (`web_research`, `doc_rag`, community plugins, and the MCP proxy
  mounts). The core-name exemption for the V1 four is UNCHANGED — they stay bare and byte-pinned.
- **Implementation timing:** Now (the T5 fix). The separator lives in ONE place — `tool_router.namespaced_name`
  — so no name is hardcoded twice; a NEW guard test validates EVERY catalog name against the API pattern (the
  missing guard that let this reach a live run — the real defect).

---

## DEC-12 (2026-07-22) — security-guard live-SOP checks must be DETERMINISTIC, not model-mediated — APPROVED

- **Item:** How the live SOP (`diag_sandbox.py`) verifies a SECURITY guard — specifically CHECK 3, the sandbox's
  secret-file refusal.
- **Reason (the failure):** The first live SOP's CHECK 3 asked the MODEL to read a planted `.env`. The model
  refused from its persona instructions and never invoked a tool (`tools=[]`), so `stage_file_gate` — the
  deterministic guard that model-provided `files[]` actually flow through — was NEVER exercised. The canary
  "passed" only because nothing was read at all: a FALSE NEGATIVE on the primary guard. Prompt-layer refusal is
  probabilistic (it shifts with phrasing, with tainted context under `web_research`, and with a different provider
  under the multi-provider protocol); the gate is deterministic. The constitution states secrets are refused BY
  NAME inside the FileReader family and that we must NEVER rely on the prompt to protect them — so a live run that
  leaves the gate untouched proves nothing. Closing an execution milestone without proving its primary guard is
  unacceptable.
- **Resolution:** Sultan's sign-off. A security guard is verified by DRIVING THE GUARD DIRECTLY, never by trusting
  model judgment. CHECK 3 is rewritten to construct a `run_code` invocation whose `files[]` carries a secret-named
  file and drive it straight through the real `SandboxService` / `stage_file_gate`, asserting on the GATE's
  behavior alone: (a) the file is refused, (b) the refusal is a short Arabic note, (c) the canary is absent from
  the tool_result, (d) the canary is absent from the logs; plus a benign-file positive control (so the refusal is
  the gate acting, not a dead pipeline). A model-mediated request is kept ONLY as a labelled OBSERVATION — never
  an acceptance criterion; a prompt-layer refusal there is fine and logged as such. A unit test
  (`tests/test_stage_file_gate.py`) mirrors the live check so CI prevents regression. GENERAL PRINCIPLE: every
  security guard's SOP check must be deterministic and must fail if the guard is removed — a check that can pass
  without exercising the guard is not a check.
- **Implementation timing:** Now (the CHECK-3 rewrite + the unit guard). Binds all future security-guard SOP
  checks (`web_research` taint/confirmation, `doc_rag` injection wrapping): exercise the guard directly.

---

## GATE FINDING (2026-07-22) — `stage_file_gate` does not basename-ify — OPEN, awaiting Sultan's ruling

- **Item:** While building the DEC-12 deterministic gate check, a SECOND gap surfaced (empirically reproduced):
  `stage_file_gate(name, data)` calls `_blocked_name(name)` on the RAW name, whereas `FileReader.read` matches on
  the BASENAME (`_blocked_name(path.name)` + the resolved target — "raw AND resolved path", symlink armor). So a
  path-PREFIXED secret name slips past the exact/prefix matchers:
  - REFUSED (correct): `.env`, `.env.local`, `id_rsa`, `credentials`, `.netrc`, `server.pem`, and — because
    `Path().suffix` is directory-agnostic — even `dir/server.pem`, `dir/private.key`.
  - NOT REFUSED (the gap): `sub/.env`, `a/b/.env`, `/tmp/.env`, `..\.env`, `sub/credentials`, `sub/id_rsa`,
    `sub/.env.local` — all return `None` from the gate.
- **Why it matters:** `stage_file_gate`'s own docstring claims "the SAME secret-name … refusals as read()", but it
  is WEAKER than `read()` for path-y names — the docstring over-claims. Severity is LOW in practice (the `files[]`
  content is model-PROVIDED, not read off the user's disk; the schema declares `files[].name` as "no directory";
  and the bootstrap's `open("/work/" + name)` fails anyway for a subdir path or a `..` traversal under
  `--read-only`). But it is a security-gate correctness gap in the very milestone whose point is to PROVE that
  gate, and "be defensive — the model chooses the path" is the FileReader family's stated posture.
- **Not guessed — logged (per the standing rule):** two candidate rulings, only Sultan decides:
  - **(1) HARDEN — make the gate match the basename**, mirroring `read()`: `_blocked_name(PurePosixPath(name).name)`
    (the container path is POSIX). Smallest change; makes the gate honor its own docstring.
  - **(2) HARDEN by REJECTING structure** — refuse any `files[].name` containing a path separator (`/` or `\`) or
    `..`, enforcing the schema's "no directory" contract at the gate (also closes the `/work/..` traversal).
    Stricter; a clearer invariant.
- **Status:** **→ CLOSED by DEC-13** (2026-07-22). At log time it was NOT acted on and
  `tests/test_stage_file_gate.py` covered only the proven BARE-name contract (the gap was not encoded as a green
  assertion); Sultan then ruled Option 2 — see DEC-13.

---

## DEC-13 (2026-07-22) — harden `stage_file_gate`: reject path structure in staged names — APPROVED (closes the GATE FINDING)

- **Item:** The GATE FINDING above — `stage_file_gate` matched secret names on the RAW name, so a path-prefixed
  secret name (`sub/.env`, `../.env`) slipped past the exact/prefix matchers into a staged sandbox file.
- **Reason:** Sultan's ruling. The "low severity" assessment was accurate TODAY but every mitigation cited was
  CIRCUMSTANTIAL, not structural: `files[]` content is model-supplied, and under `web_research` that model will be
  operating in TAINTED web context where an injection could supply `sub/.env`; the bootstrap's failure on
  subdirectories is incidental protection from a DIFFERENT layer. The constitution is explicit — guards protect BY
  CONSTRUCTION, never by coincidence; "it fails for another reason" is not a defense.
- **Resolution:** Sultan's sign-off — **Option 2 (enforce the contract), NOT Option 1 (strip/normalize).** The
  §2.1 schema already declares `files[].name` as "a file name with no directory", so the correct behavior is to
  ENFORCE that contract with an EXPLICIT refusal, not to silently normalize a malformed input. `stage_file_gate`
  now REFUSES any name containing a path separator (`/` or `\`) or a bare `..` traversal reference, with a short
  Arabic note (`FILE_NAME_NOT_BARE_AR`), BEFORE the secret-name and binary checks — closing `/work` traversal at
  the root. The existing secret-name matching is UNCHANGED (bare secrets still refuse via `FILE_BLOCKED_AR`). A
  `..` in the MIDDLE of a bare name (`archive..bak`) is a legal file name, not a traversal segment, and is
  intentionally ALLOWED (no over-rejection). Explicit refusal beats silent normalization. The `stage_file_gate`
  docstring, which had over-claimed "the SAME refusals as read()", is corrected to state the actual, stricter
  contract (read() resolves real paths; a staged name must be bare).
- **Implementation timing:** Now. `tests/test_stage_file_gate.py` gains a refusal case for EVERY demonstrated
  escape (`sub/.env`, `../.env`, `/tmp/.env`, `sub/credentials`, `sub/id_rsa`, backslash variants, bare `..`) plus
  no-over-reject cases; `diag_sandbox.py` CHECK 3 gains a deterministic live assertion that a path-prefixed secret
  name is refused — the live SOP now proves the CLOSED hole, not only the original one.
