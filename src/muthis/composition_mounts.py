# src/muthis/composition_mounts.py
"""
composition_mounts.py — where a route's KERNEL-OWNED SECURITY FACTS are stated.

THE SEAM WAS NAMED AT PLANNING TIME (DEC-52) AND ITS TRIGGER HAS NOW FIRED.
DEC-52 reserved this split when `composition.py` sat at 247/300 and measured the
growth axis honestly: not "wiring" in general, but ONE MOUNT FUNCTION PER
CAPABILITY MILESTONE — `mount_web_research` at 25 lines, `mount_doc_rag` projected
at 38. The trigger it wrote down was explicit: *the FIRST milestone whose mount
would push `composition.py` past 300 executes this extraction FIRST, alone,
byte-identical, before its feature work.* T4's mount measured the file at **320**,
so this commit is that extraction and it contains nothing else.

WHY MOUNTS AND BUILDERS SPLIT HERE, and it is a PRINCIPLED seam rather than a size
cut:
  · A **BUILDER** answers "what object exists" — `_build_broker_graph`,
    `_build_orchestrator`, `_build_sandbox`, `_size_sent_image`. Those do not grow
    per milestone, and they stay in `composition.py`.
  · A **MOUNT** states the KERNEL'S OWN facts about a route — `taint`, `impact`,
    `namespace`, `provenance`. DEC-15's rule is that these are assigned by whoever
    MOUNTS the route and never by the plugin, and DEC-51 is a ruling *about a
    mount's two flags*. That is a different question from "what object exists", and
    it is the security-critical one.

THE EVIDENCE THAT MOUNT SITES DESERVE THEIR OWN READABLE HOME is already in the
ledger: **DEC-40 found that five of six mutations survived because every test built
its OWN router — deleting the production mount call entirely stayed GREEN.** The
mount site is exactly the place where a deletion is invisible, which is the same
argument that keeps `tool_router.py`'s dispatch funnel readable whole.

`composition.py` RE-EXPORTS every name here, so every existing importer — `main.py`,
the tests, the live-SOP diag scripts — keeps working unchanged (the `turn.py` /
`highlight_gate` / `history_hygiene` re-export precedent). The function bodies are
BYTE-IDENTICAL to their `composition.py` originals; this commit moves code and
changes no behaviour.
"""

from __future__ import annotations

from .broker.net import HardenedFetcher
from .kernel.tool_router import ToolRouter
from muthis_sdk import NetCapability, PluginContext
from .trust.high_impact import NETWORK_CAPABILITY, RouteImpact


def mount_web_research(router: ToolRouter, plugin, fetcher: HardenedFetcher) -> None:
    """Mount `web__search` / `web__fetch` — the project's THIRD model-visible
    change (V1 four → v2 sandbox → v3 web), byte-pinned to look_tools_v3.json.

    Called from main AFTER the sandbox mount, so v3 is v2 with two tools APPENDED
    and the snapshot diff stays purely additive.

    IN-PROCESS, not through the broker's grant flow (DEC-33): `web_research` is a
    FIRST-PARTY NATIVE plugin like the core four and `sandbox_exec`, so it
    receives the real capability object directly. `ctx.net` IS the hardened
    fetcher's one verb — the plugin gets readable content, never a socket.

    The two facts the KERNEL states here are the ones a plugin may never state
    about itself (DEC-15): `taint=True`, because a page is external content by
    definition, and `capabilities={net.fetch}`, because that is what this root
    just granted. Both drive the DEC-16 confirmation, and `read_only=True` on the
    plugin's own descriptors cannot lower either."""
    router.mount(
        plugin,
        ctx=PluginContext(net=NetCapability(fetch_readable=fetcher.fetch_readable)),
        namespace="web",
        provenance="web_research",
        taint=True,
        impact=RouteImpact(capabilities=frozenset({NETWORK_CAPABILITY})),
    )


def mount_doc_rag(router: ToolRouter, plugin) -> None:
    """Mount `docs__open` / `docs__query` — the project's FOURTH model-visible
    change (V1 four → v2 sandbox → v3 web → v4 docs), byte-pinned to
    look_tools_v4.json. Called AFTER the web mount so v4 is v3 with two tools
    APPENDED and the snapshot diff stays purely additive.

    DEC-51 IS THIS FUNCTION'S WHOLE POINT, and the two flags travel TOGETHER:

      * **`taint=True`** because any document reaching this route is BY DEFINITION
        too large to have been inspected. The real line is not local-versus-external
        — it is whether the USER SAW IT. `read_local_file` returns a few thousand
        NUMBERED characters; the injection threshold alone exceeds a hundred pages,
        and a PDF can hide text a user never sees even with the file open. A UNIFORM
        rule is also STRONGER than one varying by zone or format, which would make
        security depend on the PARSER — the component most likely to be swapped,
        upgraded, or surprised by a malformed file.
      * **`read_only_hint=True`** because impact classification reads `taint` as the
        EXTERNALITY signal, so `taint=True` ALONE would classify this route
        high-impact and put a two-turn SPOKEN CONFIRMATION in front of reading a
        local file. DEC-32 predicted this exact coupling and asked to be re-read at
        this gate; DEC-51 is the decision it asked for, and this line spends it.

    ACCEPTED CONSEQUENCE, Sultan's ruling and not an oversight: taint is sticky
    (DEC-2), so ingesting a document TAINTS THE SESSION and any later `web__fetch`
    or networked sandbox run needs spoken approval. That is intentional — a hostile
    PDF's goal is precisely to push the model outward, which is the exact motion the
    confirmation stands in front of.

    Both facts are the KERNEL'S (DEC-15). The plugin's own `read_only=True`
    descriptors can neither raise nor lower either, and a test proves it.

    NO CAPABILITY is granted, so `high_impact`'s capability arm cannot fire either:
    reading a local document sends nothing anywhere — the V1 `read_local_file`
    argument, unchanged. `ctx` is a bare `PluginContext` for the same reason the
    sandbox mount passes none: the document service is INJECTED into the plugin
    already-built (DEC-27), so there is no capability seam for the broker to hand
    over and nothing here for a denial to make absent."""
    router.mount(
        plugin,
        ctx=PluginContext(),
        namespace="docs",
        provenance="doc_rag",
        taint=True,
        impact=RouteImpact(read_only_hint=True),
    )


def mount_navigator(router: ToolRouter, plugin) -> None:
    """Mount `navigator__plan` / `navigator__step` — the project's FIFTH
    model-visible change and catalog **v6**, byte-pinned. Mounted AFTER the doc
    mount so v6 is v5 with two tools APPENDED and the diff stays additive.

    THE TWO FLAGS ARE THE POINT, and both are the OPPOSITE of `doc_rag`'s —
    which is what makes this line the place DEC-65's invariant is SPENT rather
    than merely asserted:

      * **`taint=False`.** A mode verb ingests NOTHING. Its arguments are the
        model's own words, already in the context; no page, no document and no
        external byte crosses this route. `doc_rag` needed `taint=True` because
        a document is by definition too large to have been inspected — there is
        no analogous quantity here to be unable to inspect.
      * **NO CAPABILITY.** A mode grants no privilege, EVER. With nothing for
        `high_impact`'s capability arm to read, a mode change can never demand
        spoken approval — which matters, because a confirmation in front of
        "next step" would make the walkthrough unusable. `read_only_hint=True`
        states the KERNEL's own read of the route, exactly as DEC-51 does.

    `kernel_serviced=True` on the descriptors is why the router never executes
    these: the plugin declares the schema and the KERNEL owns the effect,
    because the state they change is the kernel's (DEC-73). The servicing branch
    and the answer-by-name arm landed BEFORE this line — DEC-39's requirement,
    not a preference."""
    router.mount(
        plugin,
        ctx=PluginContext(),
        namespace="navigator",
        provenance="navigator",
        taint=False,
        impact=RouteImpact(read_only_hint=True),
    )


def mount_navigator_verify(router: ToolRouter, plugin) -> None:
    """Mount `navigator__verify` — catalog **v8**, and an EXTENSION.

    THE SAME NAMESPACE, A SEPARATE MOUNT, AND THE SEPARATION IS THE RULING
    (DEC-108). The verb belongs to the navigator family and is exposed under its
    namespace, but it arrives through its OWN plugin so that `mount_navigator`'s
    object — the one every v7-era catalog pin builds — stays exactly what it was.
    Adding a third descriptor to `NavigatorPlugin` would have reddened those
    pins for a reason unrelated to what they protect, and the tempting repair
    (re-basing them to compare file against file) changes what they ASSERT.

    MOUNTED LAST, so v8 is v7 with ONE descriptor APPENDED and the additive
    guard shape returns after two revisions (v5, v7). Every earlier schema stays
    byte-identical by construction rather than by care.

    THE FLAGS ARE `mount_navigator`'s, unchanged, and for stronger reasons: a
    verb that only REPORTS ingests nothing (`taint=False` — its arguments are
    the model's own words about a frame already in the context) and grants
    nothing (NO CAPABILITY, so `high_impact`'s capability arm cannot fire and no
    spoken approval can ever stand in front of a verification).

    `kernel_serviced=True` on the descriptor: the plugin declares the schema and
    the KERNEL owns the effect (DEC-73). **This mount is NOT in the composition
    root yet.** DEC-39's ordering law — the servicing arm lands BEFORE the mount
    that makes a tool reachable — is why: Gate 2A builds the structure, Gate 2B
    wires the call site, and only then does the composition root call this."""
    router.mount(
        plugin,
        ctx=PluginContext(),
        namespace="navigator",
        provenance="navigator",
        taint=False,
        impact=RouteImpact(read_only_hint=True),
    )


__all__ = ["mount_doc_rag", "mount_navigator", "mount_navigator_verify",
           "mount_web_research"]
