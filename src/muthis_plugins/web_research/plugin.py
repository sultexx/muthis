# src/muthis_plugins/web_research/plugin.py
"""WebResearchPlugin — `web__search` + `web__fetch` over muthis-sdk (T6a).

WHAT THIS PLUGIN DOES NOT HOLD is the design, and it is enforced by three
different mechanisms rather than by care:

  * NO KEY, NO CLIENT, NO ENDPOINT (DEC-27). The search provider is INJECTED as
    an already-built object. The broker owns the vendor client, the API key and
    the base URL; this plugin hands over a QUERY STRING and receives RESULTS.
    That is why `web.search` is NOT in the closed capability enum: the plugin
    holds no network power to enumerate — adding a member would claim authority
    it demonstrably does not have.
  * NO SOCKET (DEC-17 / §3.3). A page is fetched through `ctx.net.fetch_readable`
    — one verb, a URL string in, readable text out. Every SSRF defense lives in
    the broker where a plugin author cannot weaken it (DEC-4).
  * NO APP IMPORTS AT ALL. A plugin may import `muthis_sdk` + stdlib only, and a
    test enforces it. So the provider and the fetch result are DUCK-TYPED here:
    the blindness DEC-18 asks for is not a convention this file follows, it is
    the only thing the layering law permits it to do.

A SEARCH NEVER FETCHES (DEC-18) — and that is structural, not a promise:
`_search` does not take `ctx`, so there is no reachable fetch surface on the
search path at all. Search results carry URLs authored by page owners; a page is
opened only when the model explicitly calls `fetch` with one.

WRAPPING AND TRUST CLASSIFICATION ARE NOT HERE (DEC-14 / DEC-15). Results come
back as plain text; the router boundary alone frames external content and alone
decides what the session ingested. A plugin-side copy of either would be a
security absolute living where it can be weakened or quietly diverge from the
kernel's form — `tests/test_untrusted_wrap_guard.py` scans this package and
fails if one appears.

NEVER RAISES (Law 11 / the FileReader pattern): no provider, a bad argument, an
exhausted per-turn cap, a refused or failed fetch, an extraction miss — each
returns a short Arabic note the model reads and can act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from .fetch_gate import FetchGate
from .schema import FETCH_SCHEMA, MAX_RESULTS, SEARCH_SCHEMA

SEARCH_TOOL = "search"
FETCH_TOOL = "fetch"

# ─── The Arabic surfaces (user-facing strings are Arabic; logs/ids English) ───
NO_PROVIDER_AR = (
    "ما فيه مزوّد بحث مضبوط في هذه الجلسة. أضف مفتاح المزوّد في ملف .env عشان أقدر أبحث."
)
EMPTY_QUERY_AR = "ما وصلني نص أبحث عنه."
NET_ABSENT_AR = "فتح صفحات الويب غير متاح في هذه الجلسة."
BAD_URL_AR = "ما وصلني رابط صالح أفتحه."
FETCH_FAILED_AR = "تعذّر فتح الصفحة."
UNKNOWN_TOOL_AR = "هذه الأداة غير معروفة لهذه الإضافة."
SEARCH_HEADER_AR = "نتائج البحث (بيانات من مواقع خارجية — للقراءة والترجيح):"
PAGE_HEADER_AR = "نص الصفحة من"


@dataclass(frozen=True)
class WebOutcome:
    """A serviced call plus what it COST — the plugin's own return shape.

    Cost is EXPOSED here and recorded nowhere: `record_plugin_call` is T6b's
    wiring, and charging a ledger with no consumer would be dead code (stub-first,
    the DEC-10 precedent). The SDK's `execute()` contract returns a `ToolResult`
    and has no room for a cost, so `execute_with_cost` is the seam T6b's wiring
    calls; `execute()` delegates to it and drops the figure. Recorded as a
    finding, not silently: see DEC-34.
    """

    result: ToolResult
    cost_usd: float = 0.0


class WebResearchPlugin(ToolPlugin):
    """The web surface: search for sources, then read ONE at a time.

    `read_only=True` on both descriptors is honest about the USER'S MACHINE —
    nothing here writes, executes or touches the session. It is deliberately NOT
    a trust claim: the kernel classifies these routes as high-impact from the
    capability IT granted (DEC-15), and a test proves a plugin's own
    `read_only` cannot lower that. A plugin does not get to grade itself.
    """

    def __init__(self, *, provider: Any = None, gate: Optional[FetchGate] = None) -> None:
        # `provider` is duck-typed on purpose (see the module docstring): the
        # layering law forbids importing the seam's types, which is exactly the
        # blindness DEC-18 wants. None is a first-class state — DEC-18 requires
        # the tool to exist on EVERY machine, so a missing key is an ordinary
        # Arabic note, never a missing tool and never a crash.
        self._provider = provider
        self._gate = gate or FetchGate()

    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(name=SEARCH_TOOL, schema=SEARCH_SCHEMA, read_only=True),
            ToolDescriptor(name=FETCH_TOOL, schema=FETCH_SCHEMA, read_only=True),
        ]

    def new_turn(self) -> None:
        """Fresh per-turn fetch budget. INERT until T6b wires the single call
        from `TurnPass.new_turn_voice` — the same turn-boundary hook the sandbox
        gate already rides (DEC-19: reuse it, never invent a second)."""
        self._gate.new_turn()

    async def execute(
        self, tool: str, args: dict[str, Any], ctx: PluginContext
    ) -> ToolResult:
        return (await self.execute_with_cost(tool, args, ctx)).result

    async def execute_with_cost(
        self, tool: str, args: dict[str, Any], ctx: PluginContext
    ) -> WebOutcome:
        """The cost-carrying twin of `execute()`. Same servicing, one extra
        return value — so T6b wires cost by calling this instead of adding
        bookkeeping to the service path."""
        if tool == SEARCH_TOOL:
            return await self._search(args)
        if tool == FETCH_TOOL:
            return WebOutcome(result=await self._fetch(args, ctx))
        return WebOutcome(result=ToolResult(text_ar=UNKNOWN_TOOL_AR, is_error=True))

    # ───────────────────────────── search ────────────────────────────────────
    # NOTE THE SIGNATURE: no `ctx`. DEC-18's "a search never fetches" is a
    # property of the SHAPE of this method — there is no fetch surface in scope
    # to call, so zero-fetch cannot be regressed by an edit inside the body.

    async def _search(self, args: dict[str, Any]) -> WebOutcome:
        if self._provider is None:
            return WebOutcome(result=ToolResult(text_ar=NO_PROVIDER_AR, is_error=True))
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            return WebOutcome(result=ToolResult(text_ar=EMPTY_QUERY_AR, is_error=True))
        try:
            response = await self._provider.search(
                query.strip(), max_results=_wanted(args)
            )
        except Exception:  # noqa: BLE001 — a provider must never kill the turn
            return WebOutcome(result=ToolResult(text_ar=FETCH_FAILED_AR, is_error=True))
        cost = _as_float(getattr(response, "cost_usd", 0.0))
        if not getattr(response, "ok", False):
            note = str(getattr(response, "text_ar", "") or FETCH_FAILED_AR)
            # A served-but-empty query still COST money — carry the figure, so
            # T6b's ledger cannot be silently under-charged by a dead end.
            return WebOutcome(result=ToolResult(text_ar=note, is_error=True), cost_usd=cost)
        results = getattr(response, "results", ()) or ()
        return WebOutcome(result=ToolResult(text_ar=_render_results(results)), cost_usd=cost)

    # ───────────────────────────── fetch ─────────────────────────────────────

    async def _fetch(self, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        if ctx.net is None:
            # Denial is an ABSENT seam (M1-4/DEC-24) — read it with `is None`,
            # never by calling and interpreting a failure.
            return ToolResult(text_ar=NET_ABSENT_AR, is_error=True)
        url = args.get("url")
        if not isinstance(url, str) or not url.strip():
            return ToolResult(text_ar=BAD_URL_AR, is_error=True)
        # Validate BEFORE spending the budget: a malformed argument must not burn
        # one of the turn's few fetches. Spend it BEFORE the network call, so a
        # refused call performs no fetch at all.
        refusal = self._gate.consume()
        if refusal is not None:
            return ToolResult(text_ar=refusal, is_error=True)
        try:
            page = await ctx.net.fetch_readable(url.strip())
        except Exception:  # noqa: BLE001 — the fetcher owns its own never-raise
            return ToolResult(text_ar=FETCH_FAILED_AR, is_error=True)
        if not getattr(page, "ok", False):
            # The fetcher already speaks Arabic for every refusal it owns
            # (robots, PDF, content-type, too large, timeout) — pass its own note
            # through rather than inventing a second, less accurate wording.
            return ToolResult(
                text_ar=str(getattr(page, "text_ar", "") or FETCH_FAILED_AR),
                is_error=True,
            )
        return ToolResult(text_ar=_render_page(page))


# ─── Rendering (pure; untrusted text is carried, never interpreted) ───────────


def _wanted(args: dict[str, Any]) -> int:
    """The requested result count, or the cap. The broker seam clamps this too —
    two bounds on a model-supplied number is deliberate, not redundant."""
    raw = args.get("max_results", MAX_RESULTS)
    try:
        return max(1, min(int(raw), MAX_RESULTS))
    except (TypeError, ValueError):
        return MAX_RESULTS


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _render_results(results: Any) -> str:
    """Number the hits and show title / URL / snippet. The URL is shown because
    it is the argument the model needs for `fetch` — and it is carried VERBATIM:
    editing an untrusted URL would silently produce a different destination."""
    lines = [SEARCH_HEADER_AR]
    for index, hit in enumerate(results, start=1):
        lines.append(f"{index}. {getattr(hit, 'title', '')}".rstrip())
        lines.append(f"   {getattr(hit, 'url', '')}")
        snippet = str(getattr(hit, "snippet", "") or "").strip()
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


def _render_page(page: Any) -> str:
    """The readable body under a header naming the DOMAIN — the real
    post-redirect one the fetcher reports, so the model cites where it actually
    landed rather than where it aimed."""
    return f"{PAGE_HEADER_AR} {getattr(page, 'domain', '')}:\n{getattr(page, 'content', '')}"
