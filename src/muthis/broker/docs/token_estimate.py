# src/muthis/broker/docs/token_estimate.py
"""
The characters-to-tokens ESTIMATE, and the measured ratio behind it.

SPLIT FROM `zones.py` (which measured 288/300 with this in it) on a real seam
rather than for line count: this file holds a MEASURED PROPERTY OF A CORPUS AND A
TOKENIZER, while `zones.py` holds a DESIGN DECISION about paths. The two change
for different reasons — a new encoder re-measures the ratio and moves nothing
else; a new zone moves the boundaries and re-measures nothing.

WHY AN ESTIMATE EXISTS AT ALL, rather than a count: this number decides the zone,
and it must be available BEFORE the encoder exists. A zone-1 document may not
touch the encoder at all (DEC-47), and the model's own tokenizer arrives WITH the
encoder — so an exact count at decision time would require loading the very thing
zone 1 is defined by never loading. The inexactness is structural, not laziness,
and the ratio below is what makes it safe in the direction that matters.

An EXACT count becomes free slightly later, during chunking, where `ZonePolicy.
exceeds_budget` uses it as a second gate — still before a single vector is
computed. This file's job is only to keep an absurd document from being chunked.

Pure stdlib, no model, no tokenizer.
"""

from __future__ import annotations

import math

# THE RATIO IS THE HIGHEST tok/char P0 MEASURED OVER ANYTHING — the MIXED
# technical document at 0.358 (`V2_ROADMAP.md`), NOT the pure-Arabic corpus PDF at
# 0.317 and not the Arabic corpus range of 0.269-0.326. That inversion is DEC-49
# ruling 5's recorded finding, and it redirects where the risk lives: markup,
# identifiers and punctuation drive token density harder than script does, so the
# expensive case is MIXED content, not Arabic. Anyone re-deriving this number must
# test against a mixed technical document, not an Arabic prose one.
#
# A CEILING, DELIBERATELY — the direction of error is the whole argument. The two
# boundaries this estimate crosses have OPPOSITE failure costs:
#   · under-estimating at the 2/3 boundary admits a document that then EXCEEDS the
#     ingestion budget. The harm is unbounded silence — the failure DEC-47 exists
#     to prevent;
#   · over-estimating at the 1/2 boundary indexes a document that could have been
#     injected. The harm is bounded — one cheap chunking pass, and retrieval at
#     82% effective recall instead of the whole text.
# An upper bound is the only choice that is safe where the harm is unbounded. The
# exposed band is narrow and STATED rather than hidden: a document whose TRUE size
# falls between inject_limit * (0.269/0.358) ~= 37,600 and 50,000 tokens can be
# over-estimated into zone 2. Zero documents in the P0 corpus fall inside it
# (909 / 9,945 / 103,187 tokens), and it is recorded as a KNOWN LIMIT with its
# candidate fix rather than silently accepted.
TOKENS_PER_CHAR_CEILING = 0.358

# The measurements the ceiling was chosen from, kept beside it so a future
# re-derivation can see what it is replacing (P0 §5, one row per text):
#   0.326 corpus md (69% ar) · 0.317 corpus pdf (97% ar) · 0.269 corpus pdf (44% ar)
#   0.358 V2_ROADMAP.md (76% ar, MIXED) · 0.295 CONTRIBUTING.md (English control)
MEASURED_RATIOS = (0.269, 0.295, 0.317, 0.326, 0.358)


def estimate_tokens(chars: int) -> int:
    """A cheap UPPER BOUND on a document's token count, from its character count.

    Cheap is the requirement, not precise — see the module docstring for why an
    exact count is unavailable at decision time, and why the error is biased up."""
    return math.ceil(max(0, chars) * TOKENS_PER_CHAR_CEILING)


__all__ = ["MEASURED_RATIOS", "TOKENS_PER_CHAR_CEILING", "estimate_tokens"]
