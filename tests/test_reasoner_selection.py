"""
test_reasoner_selection.py — the `.env` switch, and the blindness it protects.

Selection follows DEC-18's SearchProvider shape EXACTLY: one protocol, several
implementations, `.env` selection, a consumer that never learns which vendor
answered. That seam was itself built on the CloudReasoner pattern, so nothing
new was invented here — which is the point, and which is what these tests pin.

TWO PROPERTIES ARE ASSERTED THAT NOTHING ELSE COULD SEE:

  · **PARITY OF THE ROOT-FACING SURFACE.** `run()` is the contract; `warm_up_tls`
    and `aclose` are NOT on it and are deliberately not added to it (DEC-88:
    sufficient as written). They are what the composition root has always called
    on the concrete agent. The day one implementation loses one, the root has to
    branch on vendor — and the blindness the whole seam exists for is gone, with
    no test failing to say so.

  · **NO PROVIDER-SPECIFIC PERSONA TEXT EXISTS ANYWHERE.** Mut'his's laws are
    Mut'his's, not one vendor's. The identity law in particular was written
    because a model named its engine under a closed framing (DEC-88 ruling 1);
    a persona that said one thing to one vendor and another to the next would
    make that law a property of a code path rather than of the product. This is
    scanned across the persona SOURCE, so a future edit cannot introduce one
    quietly.

Run:  PYTHONPATH=src pytest tests/test_reasoner_selection.py -q
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

import pytest

from muthis.cloud.claude_agent import LOOK_SYSTEM_PROMPT, ClaudeAgent
from muthis.cloud.luna_agent import LunaAgent
from muthis.cloud.protocol import CloudReasoner
from muthis.cloud.selection import DEFAULT_REASONER, build_reasoner
from muthis.persona import resolve_system_prompt

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis"
MAIN_PY = SRC / "main.py"

# Every way a vendor could be named in prompt text — the probe's own list, plus
# the Arabic transliterations a persona would actually use.
VENDOR_TOKENS = ("openai", "gpt", "chatgpt", "claude", "anthropic", "gemini",
                 "luna", "sonnet", "opus", "أوبن", "جي بي تي", "كلود")

# The composition root's surface: the contract plus the two lifecycle calls.
ROOT_FACING = ("run", "warm_up_tls", "aclose")


@pytest.fixture(autouse=True)
def _no_reasoner_env(monkeypatch):
    """Selection is read from the environment, so the developer's own `.env`
    must not decide what these tests measure."""
    for var in ("MUTHIS_REASONER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _build(**kwargs):
    return build_reasoner(system_prompt="نص", tools=[], **kwargs)


# ═══ The switch ══════════════════════════════════════════════════════════════


def test_the_DEFAULT_is_still_anthropic():
    """**THE SECOND PROVIDER SHIPS INTEGRATED BUT NOT DEFAULT.** Which one
    answers is Sultan's call after a live run on his own hardware, so this is a
    ruling pinned as a test, not an ordering that happens to hold."""
    assert DEFAULT_REASONER == "claude"
    assert isinstance(_build(), ClaudeAgent)


@pytest.mark.parametrize("value,expected", [
    ("claude", ClaudeAgent), ("luna", LunaAgent),
    ("LUNA", LunaAgent), ("  luna  ", LunaAgent),   # case and whitespace tolerated
])
def test_the_env_var_selects_the_implementation(monkeypatch, value, expected):
    monkeypatch.setenv("MUTHIS_REASONER", value)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert isinstance(_build(), expected)


def test_an_UNRECOGNISED_name_RAISES_rather_than_answering_with_another_vendor(monkeypatch):
    """DEC-18's rule — "never silently answer with a different vendor than the
    one that was asked for" — with no degraded mode available. There is no such
    thing as a Mut'his with no reasoner, so honouring that rule can only mean
    refusing to build, at composition time, where `assert_zone_invariant()`
    already puts a broken configuration."""
    monkeypatch.setenv("MUTHIS_REASONER", "gemini")
    with pytest.raises(ValueError) as excinfo:
        _build()
    assert "claude" in str(excinfo.value) and "luna" in str(excinfo.value)


def test_NOTHING_from_the_environment_is_echoed_back(monkeypatch):
    """A user who pastes a KEY into `MUTHIS_REASONER` must not have it printed
    into a log or an exception message. The valid names are listed instead —
    which is the useful half anyway (DEC-18's no-echo rule)."""
    monkeypatch.setenv("MUTHIS_REASONER", "sk-secret-value-9999")
    with pytest.raises(ValueError) as excinfo:
        _build()
    assert "sk-secret" not in str(excinfo.value)


@pytest.mark.parametrize("name,variable", [
    ("claude", "ANTHROPIC_API_KEY"), ("luna", "OPENAI_API_KEY")])
def test_a_MISSING_KEY_WARNS_before_whatever_the_SDK_does(monkeypatch, caplog,
                                                          name, variable):
    """**THE TWO SDKs MEASURABLY DISAGREE ABOUT WHEN A MISSING KEY FAILS**:
    `AsyncAnthropic` constructs and defers to the first call, `AsyncOpenAI`
    refuses to construct outright. Neither behaviour is imposed on the other —
    forcing them into one would either turn Anthropic's late failure into a
    startup crash (a behaviour change nobody asked for) or swallow OpenAI's
    precise early error for a vaguer later one.

    What IS guaranteed, and what this asserts, is that OUR warning naming the
    exact variable is emitted FIRST, so the log reads identically either way."""
    monkeypatch.setenv("MUTHIS_REASONER", name)
    with caplog.at_level("WARNING", logger="muthis.cloud"):
        try:
            _build()
        except Exception:                      # noqa: BLE001 — the SDK's own call
            pass
    assert f"{variable} is empty" in caplog.text


def test_the_selected_model_is_logged_for_ATTRIBUTION(monkeypatch, caplog):
    """`TurnComplete` carries `model` for exactly this reason. Blind means the
    ORCHESTRATOR does not branch on the vendor — not that nobody may write down
    which one answered."""
    monkeypatch.setenv("MUTHIS_REASONER", "luna")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with caplog.at_level("INFO", logger="muthis.cloud"):
        _build()
    assert "reasoner=luna" in caplog.text and "gpt-5.6-luna" in caplog.text


# ═══ The blindness ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("agent_class", [ClaudeAgent, LunaAgent])
def test_both_implementations_satisfy_the_UNCHANGED_protocol(agent_class):
    """`cloud/protocol.py` is byte-untouched by this integration — DEC-88
    measured it against this exact provider and found it SUFFICIENT AS WRITTEN."""
    assert isinstance(agent_class(api_key="test-key"), CloudReasoner)


@pytest.mark.parametrize("method", ROOT_FACING)
def test_both_implementations_expose_the_SAME_root_facing_surface(method):
    """If one loses a method the composition root must branch on vendor, and the
    seam's whole claim dies quietly. Asserted on both so neither can drift."""
    for agent_class in (ClaudeAgent, LunaAgent):
        assert callable(getattr(agent_class, method, None)), (
            f"{agent_class.__name__} has no {method}() — the composition root "
            "would have to learn which vendor it built")


def test_both_take_the_SAME_constructor_keywords():
    """The root builds either without branching, and that costs exactly one
    parameter list. A keyword present on one and absent on the other is a branch
    waiting to be written."""
    shared = {"api_key", "model", "max_tokens", "system_prompt", "tools", "http_client"}
    for agent_class in (ClaudeAgent, LunaAgent):
        params = set(inspect.signature(agent_class.__init__).parameters)
        assert shared <= params, f"{agent_class.__name__} is missing {shared - params}"


def test_the_composition_root_names_NO_vendor_class():
    """Scanned by SOURCE, because no test may import `muthis.main` (it calls
    `load_dotenv()` at module level and would pull the developer's real
    credentials into the test process — the standing rule, and the
    `test_logging_privacy.py` AST precedent)."""
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "build_reasoner(" in source
    for vendor_class in ("ClaudeAgent(", "LunaAgent("):
        assert vendor_class not in source, (
            f"main.py constructs {vendor_class} directly — the root has learned "
            "which vendor it is talking to")


# ═══ The persona is Mut'his's, not a vendor's ════════════════════════════════


PERSONA_SOURCES = ("persona.py", "persona_rules.py")


def _prompt_literals(path: pathlib.Path) -> list[tuple[int, str]]:
    """Every string literal that is NOT a docstring — i.e. everything that could
    reach the composed prompt.

    Parsed rather than grepped, and the distinction is the whole design: a
    docstring or a comment MAY discuss a vendor (the rationale for the identity
    law has to be readable, and this very file names four), while a string that
    could reach the model MAY NOT. A line-based scan cannot tell those apart and
    would force the rationale out of the code to stay green."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def test_NO_provider_specific_persona_text_exists_anywhere():
    """**The identity law is a Mut'his law, not a Claude one.** It was written
    because a model named its engine under a closed framing (DEC-88 ruling 1),
    and it held mid-conversation on the second provider under the same framing
    (DEC-90). Both of those are statements about the PRODUCT — and they stop
    being that the moment one vendor's path carries a sentence the other's does
    not.

    Note what this forbids in BOTH directions: not only "you are Claude", but
    also a rule phrased as "never say you are GPT". A law that ENUMERATES the
    vendor it denies is a cutoff (the M16 family) — it covers the names someone
    thought of, and DEC-89 ruling 1 already established that the working form
    refuses the FRAMING rather than listing the answers."""
    offenders = []
    for name in PERSONA_SOURCES:
        path = SRC / name
        for lineno, text in _prompt_literals(path):
            for token in VENDOR_TOKENS:
                if re.search(rf"\b{re.escape(token)}\b", text, re.IGNORECASE):
                    offenders.append(f"{name}:{lineno}: {token!r} in a prompt literal")
    assert not offenders, (
        "provider-specific text reached the persona:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("token", VENDOR_TOKENS)
def test_the_COMPOSED_PROMPT_names_no_vendor(token):
    """The scan above reads SOURCE; this reads the BYTES that go on the wire —
    the real composed persona, resolved exactly as `main.py` resolves it. It is
    the stronger of the two: a vendor name assembled at runtime out of pieces no
    literal contains would pass the source scan and fail here."""
    prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, 1280, 720)
    assert not re.search(rf"\b{re.escape(token)}\b", prompt, re.IGNORECASE), (
        f"the composed persona names {token!r}")


def test_the_composed_prompt_test_is_reading_a_REAL_persona():
    """The positive control for the test above: an empty or fallback-only prompt
    would satisfy every vendor assertion by containing nothing at all."""
    prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, 1280, 720)
    assert len(prompt) > 5_000, f"the composed persona is only {len(prompt)} chars"
    assert "مطحس" in prompt


def test_the_guard_above_is_actually_reading_prompt_text():
    """THE POSITIVE CONTROL (the DEC-50 cutoff rule). A parse that yielded
    nothing — a renamed file, a changed layout — would make the scan above pass
    while examining NOTHING, which is indistinguishable from a clean persona."""
    literals = [t for name in PERSONA_SOURCES for _, t in _prompt_literals(SRC / name)]
    # Measured in CHARACTERS, not in literals: the persona is a handful of long
    # multi-line strings, so a literal COUNT would be a threshold on formatting.
    scanned = sum(len(text) for text in literals)
    assert scanned > 5_000, f"only {scanned} chars of prompt text scanned"
    assert any("مطحس" in text for text in literals), (
        "the scan found no Arabic persona text at all — it is not looking at "
        "the prompt")


def test_both_wrappers_default_to_the_SAME_system_prompt():
    """One fallback persona, shared BY IDENTITY — not two copies that could
    drift apart one law at a time."""
    defaults = [inspect.signature(cls.__init__).parameters["system_prompt"].default
                for cls in (ClaudeAgent, LunaAgent)]
    assert defaults[0] is defaults[1] is LOOK_SYSTEM_PROMPT


def test_the_agents_hold_NO_persona_text_of_their_own():
    """`LOOK_SYSTEM_PROMPT` lives in ONE module and is imported, never restated.
    A wrapper carrying its own Arabic would be provider-specific persona text by
    construction, whatever it said."""
    source = (SRC / "cloud" / "luna_agent.py").read_text(encoding="utf-8")
    arabic = [line for line in source.splitlines()
              if any("؀" <= ch <= "ۿ" for ch in line)]
    assert not arabic, f"the Luna wrapper carries its own Arabic: {arabic}"
