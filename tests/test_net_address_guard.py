# tests/test_net_address_guard.py
"""Address guard (DEC-17) — the SSRF validator, built + tested FIRST. It is
IP-OBJECT based, never string matching; a dict-backed fake resolver stands in
for DNS so the suite needs no network. Each test FAILS if its guard is removed
(DEC-12): drop the resolved-IP check and the decimal/private cases pass a
PinnedRequest instead of a refusal."""

from __future__ import annotations

import pytest

from muthis.broker.net.address_guard import (
    BAD_URL_AR,
    BLOCKED_ADDRESS_AR,
    SCHEME_AR,
    UNRESOLVABLE_AR,
    ip_block_reason,
    validate_and_pin,
)


def _resolver(mapping):
    def resolve(hostname, port):
        return mapping[hostname]

    return resolve


# ── scheme allowlist ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "data:text/html,hi", "gopher://x/1",
     "ftp://h/f", "ws://h/s", "javascript:alert(1)"],
)
def test_non_http_schemes_refused(url):
    pinned, note = validate_and_pin(url, resolver=_resolver({}))
    assert pinned is None and note == SCHEME_AR


def test_http_and_https_allowed():
    for scheme in ("http", "https"):
        pinned, note = validate_and_pin(
            f"{scheme}://ok.example/p", resolver=_resolver({"ok.example": ["104.20.23.154"]})
        )
        assert note is None and pinned is not None and pinned.scheme == scheme


# ── IP-object blocks (literal hosts) ─────────────────────────────────────────
@pytest.mark.parametrize(
    "host,label",
    [
        ("127.0.0.1", "loopback"),
        ("10.0.0.5", "private-10"),
        ("192.168.1.1", "private-192"),
        ("172.16.5.5", "private-172"),
        ("169.254.169.254", "link-local cloud-metadata"),
        ("100.64.1.1", "cgnat non-global"),
        ("0.0.0.0", "unspecified"),
        ("[::1]", "ipv6 loopback"),
        ("[fe80::1]", "ipv6 link-local"),
        ("[fc00::1]", "ipv6 ula"),
        ("[::ffff:127.0.0.1]", "ipv4-mapped loopback"),
        ("[::ffff:10.0.0.1]", "ipv4-mapped private"),
        ("[2002:7f00:1::]", "6to4 wrapping loopback"),
    ],
)
def test_internal_ip_literals_blocked(host, label):
    pinned, note = validate_and_pin(f"http://{host}/", resolver=_resolver({}))
    assert pinned is None and note == BLOCKED_ADDRESS_AR, label


def test_public_ip_literal_allowed():
    pinned, note = validate_and_pin("http://104.20.23.154/p", resolver=_resolver({}))
    assert note is None and pinned.connect_ip == "104.20.23.154"


# ── the decimal trick: the STRING is not an IP, the RESOLVER reads it as
#    loopback — only validating the RESOLVED object catches it ────────────────
def test_decimal_encoded_host_blocked_via_resolved_ip():
    resolver = _resolver({"2130706433": ["127.0.0.1"]})
    pinned, note = validate_and_pin("http://2130706433/", resolver=resolver)
    assert pinned is None and note == BLOCKED_ADDRESS_AR


def test_name_resolving_to_private_blocked():
    resolver = _resolver({"evil.example": ["10.1.2.3"]})
    pinned, note = validate_and_pin("https://evil.example/", resolver=resolver)
    assert pinned is None and note == BLOCKED_ADDRESS_AR


def test_mixed_resolution_any_bad_ip_blocks():
    # A host resolving to BOTH a public and a private address (the rebinding
    # shape) is refused outright — we validate EVERY resolved IP.
    resolver = _resolver({"mix.example": ["104.20.23.154", "127.0.0.1"]})
    pinned, note = validate_and_pin("https://mix.example/", resolver=resolver)
    assert pinned is None and note == BLOCKED_ADDRESS_AR


# ── the pin preserves host + SNI while connecting to the validated IP ─────────
def test_pin_preserves_host_and_sni():
    resolver = _resolver({"example.com": ["104.20.23.154"]})
    pinned, note = validate_and_pin("https://example.com/path?q=1", resolver=resolver)
    assert note is None
    assert pinned.connect_ip == "104.20.23.154"
    assert pinned.host_header == "example.com"
    assert pinned.sni_hostname == "example.com"
    assert "104.20.23.154" in pinned.pinned_url and "q=1" in pinned.pinned_url


def test_http_has_no_sni():
    resolver = _resolver({"example.com": ["104.20.23.154"]})
    pinned, _ = validate_and_pin("http://example.com/", resolver=resolver)
    assert pinned.sni_hostname is None


def test_nondefault_port_kept_in_host_header_and_url():
    resolver = _resolver({"example.com": ["104.20.23.154"]})
    pinned, _ = validate_and_pin("https://example.com:8443/", resolver=resolver)
    assert pinned.port == 8443 and pinned.host_header == "example.com:8443"
    assert "104.20.23.154:8443" in pinned.pinned_url


def test_public_ipv6_literal_bracketed():
    pinned, note = validate_and_pin(
        "https://[2001:4860:4860::8888]/p", resolver=_resolver({})
    )
    assert note is None and "[2001:4860:4860::8888]" in pinned.pinned_url


# ── malformed / unresolvable ─────────────────────────────────────────────────
def test_empty_host_is_bad_url():
    pinned, note = validate_and_pin("https:///path", resolver=_resolver({}))
    assert pinned is None and note == BAD_URL_AR


def test_bad_port_is_bad_url():
    pinned, note = validate_and_pin("https://h.example:notaport/", resolver=_resolver({}))
    assert pinned is None and note == BAD_URL_AR


def test_unresolvable_host_is_a_note():
    def boom(hostname, port):
        raise OSError("nxdomain")

    pinned, note = validate_and_pin("https://nope.example/", resolver=boom)
    assert pinned is None and note == UNRESOLVABLE_AR


def test_empty_resolution_is_a_note():
    pinned, note = validate_and_pin("https://void.example/", resolver=_resolver({"void.example": []}))
    assert pinned is None and note == UNRESOLVABLE_AR


# ── ip_block_reason as a direct unit ─────────────────────────────────────────
@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.1", "192.168.0.1", "169.254.169.254", "::1",
     "fe80::1", "::ffff:169.254.169.254", "2002:7f00:1::", "224.0.0.1"],
)
def test_ip_block_reason_flags_internal(ip):
    assert ip_block_reason(ip) is not None


@pytest.mark.parametrize("ip", ["104.20.23.154", "8.8.8.8", "2001:4860:4860::8888"])
def test_ip_block_reason_passes_public(ip):
    assert ip_block_reason(ip) is None
