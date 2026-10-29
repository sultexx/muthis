# src/muthis/instructions/__init__.py
"""
The instruction registry — SHADOW STEP 1 of the instruction rebuild (DEC-157 ①).

WHAT IT IS. `registry.json` holds TODAY's composed persona prompt — the text
`persona.build_saudi_persona_prompt(w, h)` returns, in today's order — cut into
DEC-139's 106 clauses with every byte between them kept as a separator.
`manifest.json` gives each entry one row: its hash, its length, and the DEC it
was ruled under, or `pre-ledger`. It is NOT the 27-law design: this step proves
the mechanism on text that is already known; the new architecture is the next
step. Kernel notes and tool descriptions are out of scope.

WHAT IT IS NOT. It is not wired. Production composes from the persona modules,
which this step did not touch, and nothing in the app imports this package
(`tests/test_instruction_registry.py` checks that by scanning `src/`).

A DECLARED, TEMPORARY SECOND SOURCE (Sultan's ruling, DEC-157 ①). Every law
now exists twice: in its persona module and in `registry.json`. The seven "one
home" tests (`test_ack_scope.py:145` and six `test_persona_*` tests) still pass,
but BY THEIR LETTER, NOT THEIR INTENT: they scan `src/**/*.py` for a law's text,
and the registry is a data file, so they cannot see the second copy, which is
exactly the drift they exist to prevent. What keeps the copy honest while it
exists is the equality test: the registry renders to production's composed
prompt byte for byte at more than one screen size (the sent-image clause is a
template), and all ten prefix anchors match the rendering. An edit to a persona
module therefore reddens that test until the registry carries the same edit.

THE OLD SOURCE RETIRES ONLY AT THE SWITCH, which will be proven by nonce-masked,
per-pass request-body equality (DEC-157 ①). Until then no old test or guard is
retired.
"""
