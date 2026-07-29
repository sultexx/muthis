# tests/test_net_capability.py
"""
The `ctx.net` seam (V2 Phase 2 M2, T6a — DEC-24), mutation-verified.

THE PROPERTY UNDER TEST IS BINARY, and it is the whole point of the commit:
granted → the seam is PRESENT; denied → the seam is ABSENT. No third state.
DEC-24(b) records why that mattered here specifically — `net.fetch` sat in the
broker's "granted-but-unwired" subtraction set from T2 until now, so a plugin
GRANTED the capability and a plugin DENIED it saw exactly the same thing and the
same silence. That is the undefined third state M1-4 forbids ("denial = an
ABSENT seam, never a different API" presumes the grant, when wired, PRODUCES
the seam). So both directions are asserted, and asserted TOGETHER as one
statement per world, so a mutation cannot satisfy one and quietly skip the other.

The second property is SHAPE (§3.3 / DEC-17): a plugin receives ONE verb taking
a URL string. No socket, no client, no base URL, no header/method surface —
nothing it could use to CONSTRUCT a request. That is asserted structurally
rather than argued, because "we did not add one" is not a guarantee.

No test here imports `muthis.main` (standing rule): the composition root runs
`load_dotenv()` at module level and would pull real credentials — including a
live TAVILY_API_KEY — into the test process. The root is checked by AST scan.
"""

from __future__ import annotations

import ast
import inspect
import logging
import pathlib

import pytest

from muthis.broker.broker import Broker
from muthis.broker.grants import GrantsStore
from muthis_sdk import CAPABILITIES, NetCapability, PluginContext, load_manifest

COMPOSITION_PY = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis" / "composition.py"
)

MANIFEST_NET = """
[plugin]
name    = "webby"
version = "1.0.0"
sdk     = ">=2.0.0a3,<3"
kind    = "native"
entry   = "webby.plugin:WebbyPlugin"

[descriptions]
ar = "إضافة تجريبية تطلب الشبكة"

[capabilities]
required = ["net.fetch"]

[tools.webby_tool]
read_only = true
"""

# The DENIED world differs from the granted one in EXACTLY one way: the plugin
# never asked for net.fetch. Everything else — the broker, the wired fetcher,
# the grant record — is identical, so the two assertions below isolate the
# capability check itself and nothing else.
MANIFEST_NO_NET = MANIFEST_NET.replace(
    'required = ["net.fetch"]', 'required = ["perceive.files.read"]'
)

SENTINEL = object()  # what the wired seam returns, so "reached it" is unambiguous


def _world(tmp_path, manifest_text=MANIFEST_NET, *, wire_fetcher=True):
    """A broker exactly as the composition root builds one, minus the real
    fetcher. `calls` records what the seam was handed, so the URL can be proven
    to pass through verbatim — a plugin supplies a string and nothing else."""
    d = tmp_path / "webby"
    d.mkdir(parents=True)
    (d / "muthis-plugin.toml").write_text(manifest_text, encoding="utf-8")
    manifest = load_manifest(d)
    grants = GrantsStore(grants_file=tmp_path / "grants.json")
    grants.grant(manifest, d)
    calls: list[str] = []

    async def net_seam(url):
        calls.append(url)
        return SENTINEL

    async def read_seam(args):
        return "من النواة"

    broker = Broker(
        grants=grants,
        read_file=read_seam,
        net_fetch=net_seam if wire_fetcher else None,
    )
    return broker, manifest, d, calls


# ─── THE BINARY CONTRACT — both directions, in one statement each ────────────


def test_a_granted_plugin_gets_the_seam_and_a_denied_one_does_not(tmp_path):
    """The DEC-24 contract as a single equality per world. Written this way on
    purpose: two separate tests could be satisfied by a mutation that hard-codes
    one answer, while `(seam present) == (capability granted)` cannot."""
    granted_broker, granted_manifest, granted_dir, _ = _world(tmp_path / "a")
    denied_broker, denied_manifest, denied_dir, _ = _world(
        tmp_path / "b", manifest_text=MANIFEST_NO_NET
    )

    granted_ctx = granted_broker.context_for(granted_manifest, granted_dir)
    denied_ctx = denied_broker.context_for(denied_manifest, denied_dir)

    assert ("net.fetch" in granted_manifest.capabilities_required) is True
    assert ("net.fetch" in denied_manifest.capabilities_required) is False
    assert (granted_ctx.net is not None) is True, "granted → the seam must be PRESENT"
    assert (denied_ctx.net is not None) is False, "denied → the seam must be ABSENT"


def test_denial_is_an_absent_seam_never_a_stub_that_refuses(tmp_path):
    """M1-4's actual words. A refusing stub would be a DIFFERENT API for a denied
    plugin — the plugin would have to call and interpret a failure instead of
    reading `ctx.net is None`. So the denied context must expose no object at
    all, and nothing on it that could be called."""
    broker, manifest, d, _ = _world(tmp_path, manifest_text=MANIFEST_NO_NET)
    ctx = broker.context_for(manifest, d)

    assert ctx.net is None
    assert not hasattr(ctx.net, "fetch_readable")
    # ...and no OTHER attribute smuggles a fetch in. `net` is the single named
    # home for the capability, so a denied plugin has nowhere else to look.
    with_fetch = [
        name for name in dir(ctx)
        if not name.startswith("_") and hasattr(getattr(ctx, name), "fetch_readable")
    ]
    assert with_fetch == [], f"an unexpected fetch surface on the context: {with_fetch}"


def test_an_ungranted_plugin_gets_no_seam_even_though_the_fetcher_is_wired(tmp_path):
    """The grant is load-bearing, not the wiring. A manifest that never asked
    for net.fetch must not receive it just because the root built a fetcher —
    this is what fails if the capability check is dropped from the branch."""
    broker, manifest, d, calls = _world(tmp_path, manifest_text=MANIFEST_NO_NET)
    assert broker.context_for(manifest, d).net is None
    assert calls == []


@pytest.mark.asyncio
async def test_the_wired_seam_reaches_the_real_fetcher_with_the_url_verbatim(tmp_path):
    """The seam is a pass-through, not a re-implementation: the plugin's URL
    string arrives at the broker's fetcher unchanged, and the fetcher's own
    result comes back unchanged. Anything else would mean the broker is
    interpreting a URL — the job DEC-17 gives the fetcher alone."""
    broker, manifest, d, calls = _world(tmp_path)
    ctx = broker.context_for(manifest, d)

    result = await ctx.net.fetch_readable("https://docs.example.com/a?q=1")

    assert calls == ["https://docs.example.com/a?q=1"]
    assert result is SENTINEL


# ─── DEC-24(b): net.fetch LEFT the granted-but-unwired subtraction set ───────


def test_a_granted_but_unwired_net_fetch_is_no_longer_swallowed(tmp_path, caplog):
    """While `net.fetch` sat in the subtraction set, a root that never built a
    fetcher produced a granted plugin with an absent seam and NO diagnostic —
    the silent third state. Now it surfaces. Restoring the entry makes the
    granted-but-unwired line disappear and this test goes RED."""
    broker, manifest, d, _ = _world(tmp_path, wire_fetcher=False)
    with caplog.at_level(logging.INFO, logger="muthis.broker"):
        ctx = broker.context_for(manifest, d)

    assert ctx.net is None  # unwired still means absent — never a stub
    unwired = [r.getMessage() for r in caplog.records if "granted-but-unwired" in r.getMessage()]
    assert unwired, "a granted-but-unwired net.fetch must be reported, not swallowed"
    assert "net.fetch" in unwired[0]


def test_the_wired_seam_is_not_reported_as_unwired(tmp_path, caplog):
    """The positive control for the test above: once wired, net.fetch must be
    subtracted by the WIRED tuple, so the diagnostic stays quiet. Without this,
    the test above would still pass if the line fired unconditionally."""
    broker, manifest, d, _ = _world(tmp_path)
    with caplog.at_level(logging.INFO, logger="muthis.broker"):
        broker.context_for(manifest, d)

    assert not [r for r in caplog.records if "granted-but-unwired" in r.getMessage()]


# ─── SHAPE: one verb, and no way to construct a request ──────────────────────


def test_the_capability_exposes_exactly_one_verb_and_no_construction_surface():
    """§3.3 as structure. A base URL, a client, a session or a header/method
    parameter would each hand a plugin a way to AIM a request — the property
    DEC-17 spends the whole fetcher defending. Pinning the public surface makes
    adding one a test failure rather than a code review's job."""
    seam = NetCapability(fetch_readable=lambda url: None)
    public = {name for name in vars(seam) if not name.startswith("_")}
    assert public == {"fetch_readable"}

    forbidden = {"client", "session", "base_url", "host", "headers", "method",
                 "transport", "socket", "connect", "request"}
    assert not (forbidden & {n for n in dir(seam) if not n.startswith("_")})

    # The verb takes a URL and nothing else — no per-call override of any of the
    # above can be smuggled in as a keyword.
    params = list(inspect.signature(NetCapability.__init__).parameters)
    assert params == ["self", "fetch_readable"]


def test_the_context_gained_net_and_nothing_else():
    """The plugin-facing surface is a contract; this pins what T6a added to it,
    so a later commit cannot widen the context quietly."""
    fields = {f for f in PluginContext.__dataclass_fields__}
    assert fields == {"files", "screen", "net", "locale", "logger"}
    assert PluginContext().net is None  # absent by DEFAULT — fail-closed


def test_the_closed_capability_enum_is_unchanged():
    """DEC-27: the provider reaches the plugin by INJECTION, so `web.search` must
    NOT appear here — adding a member is a constitutional amendment, and claiming
    a network power the plugin does not hold would be the category error the
    ruling names. `net.fetch` was already a member; T6a wires it, never adds it."""
    assert "net.fetch" in CAPABILITIES
    assert "web.search" not in CAPABILITIES
    assert CAPABILITIES == frozenset({
        "perceive.screen", "perceive.files.read", "annotate.overlay",
        "speak.caption", "net.fetch", "sandbox.execute", "cache.session",
    })


# ─── The composition root, by SOURCE SCAN (never an import) ──────────────────


def test_the_composition_root_builds_the_fetcher_and_injects_it_into_the_broker():
    """AST, not an import: `composition.py` is reached from `muthis.main`, which
    runs `load_dotenv()` at module level (the `test_session_taint.py` precedent).
    Without this, the binary contract could hold perfectly in the broker while
    production never wires a fetcher — every plugin silently denied."""
    tree = ast.parse(COMPOSITION_PY.read_text(encoding="utf-8"))
    built = any(
        isinstance(n, ast.Call) and getattr(n.func, "id", "") == "HardenedFetcher"
        for n in ast.walk(tree)
    )
    injected = any(
        isinstance(n, ast.Call)
        and getattr(n.func, "id", "") == "Broker"
        and any(kw.arg == "net_fetch" for kw in n.keywords)
        for n in ast.walk(tree)
    )
    assert built, "the composition root no longer builds a HardenedFetcher"
    assert injected, "the composition root no longer injects net_fetch into the Broker"
