# src/muthis/cloud/selection.py
"""
selection.py — which reasoner answers, chosen in `.env`.

**THE SHAPE IS DEC-18's, DELIBERATELY UNCHANGED**: one protocol, several
implementations, `.env` selection, a BLIND consumer. That seam was built on the
CloudReasoner pattern in the first place, was proven sufficient at M2, and is
now returned to the layer it was copied from. No new pattern and no new
abstraction were invented for the second reasoner, because the measurement said
none was needed.

SELECTION IS CONFIGURATION, AND CONFIGURATION IS THE OWNER'S. Nothing here is
reachable from a tool argument, from model output or from fetched content: the
machine's owner picks a vendor before any turn runs. That is the same property
`broker/search/selection.py` enforces for the key-bearing search client, and it
matters for the same reason — a tainted model must never be able to aim a
credential.

WHY A MISCONFIGURATION RAISES HERE, WHERE THE SEARCH SEAM DEGRADES.
`NoSearchProvider` exists because a missing search key leaves Mut'his able to do
everything else; it answers with a short Arabic note and the session continues.
**There is no such thing as a Mut'his with no reasoner** — every turn goes
through one. So the two rules DEC-18 states resolve differently here:
  · "never silently answer with a different vendor than the one that was asked
    for" — still binding, and with no degraded mode left it can only be honoured
    by REFUSING to build.
  · the failure therefore lands at COMPOSITION time, before the event loop
    opens, exactly where `assert_zone_invariant()` puts a broken configuration
    (`main.main()`): a configuration error stops the process legibly instead of
    surfacing later as one strange turn.
AN EMPTY KEY IS A DIFFERENT CASE AND ONLY WARNS HERE — because what happens
NEXT is the vendor SDK's decision, and **the two SDKs measurably disagree**:
`AsyncAnthropic` constructs fine and defers the failure to the first call, while
`AsyncOpenAI` REFUSES TO CONSTRUCT (`OpenAIError: Missing credentials`). Neither
behaviour is imposed on the other. Turning Anthropic's late failure into a
startup crash would be a behaviour change this task did not ask for, and
swallowing OpenAI's early one would replace a precise error with a vaguer one
later. What this function guarantees is that OUR warning — naming the exact
variable — is emitted BEFORE either outcome, so the log reads the same way
whichever vendor was selected.

NOTHING IS ECHOED FROM THE ENVIRONMENT — not into a log and not into the
exception message. An unrecognised value is answered with the list of VALID
names, which is the useful half anyway; a user who pastes a key into the wrong
variable must not have it printed back at them.

THE ROOT-FACING SURFACE IS `run()` PLUS TWO LIFECYCLE METHODS. `run()` is the
contract (`protocol.py`, untouched — DEC-88 found it sufficient as written).
`warm_up_tls()` and `aclose()` are not ON that contract and are not added to it:
they are what the composition root has always called on the concrete agent, and
BOTH implementations provide them, so the root still never branches on vendor.
`tests/test_reasoner_selection.py` asserts that parity — the day one
implementation loses a method, the root would have to branch, and the blindness
would be gone.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from .claude_agent import ClaudeAgent
from .luna_agent import LunaAgent
from .protocol import CloudReasoner

logger = logging.getLogger("muthis.cloud")

Builder = Callable[..., CloudReasoner]

# name -> (the .env key it needs, how to build it). The KEY NAME is a constant
# declared here, never a value read out of the environment.
_REASONERS: dict[str, tuple[str, Builder]] = {
    "claude": ("ANTHROPIC_API_KEY", ClaudeAgent),
    "luna": ("OPENAI_API_KEY", LunaAgent),
}

# The default when `MUTHIS_REASONER` is unset. It is Anthropic, and that is a
# RULING rather than an ordering: the second provider ships INTEGRATED but not
# DEFAULT, and the switch is Sultan's to make after a live run on his hardware.
DEFAULT_REASONER = "claude"


def build_reasoner(
    *, system_prompt: str, tools: list[dict[str, Any]]
) -> CloudReasoner:
    """Build the reasoner this machine is configured for.

    Raises `ValueError` on an unrecognised `MUTHIS_REASONER`, at composition
    time — see the module docstring for why this one refuses instead of
    degrading. A vendor SDK may additionally raise on a missing key; the warning
    below is emitted first either way.
    """
    chosen = os.getenv("MUTHIS_REASONER", "").strip().lower() or DEFAULT_REASONER
    entry = _REASONERS.get(chosen)
    if entry is None:
        raise ValueError(
            "MUTHIS_REASONER is not a known reasoner (expected one of "
            f"{sorted(_REASONERS)}) — fix .env before starting")
    key_name, build = entry
    if not os.getenv(key_name, "").strip():
        logger.warning("[cloud] reasoner=%s selected but %s is empty in .env"
                       " — the first turn will fail to authenticate", chosen, key_name)
    agent = build(system_prompt=system_prompt, tools=tools)
    # The ONE line that names the answering vendor, the way the search seam logs
    # its provider and `TurnComplete` carries `model`: for attribution, never for
    # the kernel to branch on. Blind means the ORCHESTRATOR does not know, not
    # that nobody may write it down.
    logger.info("[cloud] reasoner=%s model=%s", chosen, agent.model)
    return agent


__all__ = ["build_reasoner", "DEFAULT_REASONER"]
