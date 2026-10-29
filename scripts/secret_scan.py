"""Read-only full-history secret scan. NEVER prints a matched value.

Scans EVERY object in the repository's object store (`--batch-all-objects`:
every blob of every revision including deleted files, every commit message,
every tag annotation, reachable or not), with value-shaped detectors, and
reports only: coverage counts, per-detector counts, and per match the detector,
object id, object type, the path(s) it appeared at, the value's LENGTH and
Shannon entropy, and booleans. The value itself never leaves this process.

Usage: secret_scan.py <repo> <mode>   mode = control | scan
  control: <repo> is an EMPTY work directory; a scratch repository is built in it
  scan:    <repo> is the repository to scan (the standing pre-push run: `.`)

RUN THE CONTROL FIRST, EVERY TIME. A history-wide scan that finds nothing is
indistinguishable from a broken scan; the control plants one value per detector
in a file that is then DELETED, plus one in a commit message, and requires this
same pipeline to find all twelve. `tests/test_secret_scan.py` runs it in the
suite too. A clean scan of this repository reports exactly one distinct value:
the `tvly-` SENTINEL_KEY canary in `tests/test_search_provider.py`.

IN THE TREE SINCE DEC-157's round. It had lived only in session scratch folders,
and was lost with one -- a standing safety procedure on a PUBLIC repository
whose tool could vanish. Every planted value is ASSEMBLED at runtime, never
written out whole, so a scan of this file finds nothing in it.
"""
import collections
import math
import pathlib
import re
import subprocess
import sys

DETECTORS = {
    "anthropic_key": rb"sk-ant-[A-Za-z0-9_\-]{20,}",
    "openai_key": rb"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}",
    "google_api_key": rb"AIza[0-9A-Za-z_\-]{35}",
    "elevenlabs_key": rb"\bsk_[0-9a-f]{40,}",
    "xi_api_key_value": rb"(?i)xi-api-key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{20,}",
    "tavily_key": rb"tvly-[A-Za-z0-9_\-]{20,}",
    "brave_key": rb"\bBSA[A-Za-z0-9_\-]{25,}",
    "github_token": rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,}",
    "aws_access_key": rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "slack_token": rb"xox[baprs]-[A-Za-z0-9\-]{10,}",
    "private_key_block": rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----",
    "env_style_assignment": (rb"(?m)^[ \t]*(?:export[ \t]+)?[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)"
                             rb"[A-Z0-9_]*[ \t]*=[ \t]*[\"']?[A-Za-z0-9_\-./+=]{16,}"),
}
# The stray branch's own name, as a command: a KEYWORD search. It matches the
# WORDS (code, prose, this project's own docs about secrets), so it is counted,
# never classified — it is not a value detector.
BRANCH_COMMAND = rb"(?i)sk-ant|xi-api-key|AIza|api[_-]key|secret"
SECRET_PATHS = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|.*\.key|id_rsa.*|id_ed25519.*|"
                          r"credentials\.json|.*\.p12|.*\.pfx|\.netrc|\.npmrc|\.pypirc)$")
SYNTHETIC_MARKERS = re.compile(rb"(?i)canary|sentinel|fake|dummy|test|example|xxxx|0123456789|abcdefgh")

COMPILED = {k: re.compile(v) for k, v in DETECTORS.items()}
BRANCH_RE = re.compile(BRANCH_COMMAND)


def git(repo, *args, data=None) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], input=data,
                          capture_output=True, check=True).stdout


def entropy(b: bytes) -> float:
    counts = collections.Counter(b)
    return -sum(c / len(b) * math.log2(c / len(b)) for c in counts.values())


def objects(repo):
    listing = git(repo, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)")
    return [ln.split() for ln in listing.decode().splitlines() if ln.strip()]


def path_map(repo):
    """blob/tree id -> every path it appeared at, over every ref."""
    paths = collections.defaultdict(set)
    for ln in git(repo, "rev-list", "--all", "--objects").decode("utf-8", "replace").splitlines():
        sha, _, path = ln.partition(" ")
        if path:
            paths[sha].add(path)
    return paths


def read_all(repo, shas):
    """Stream object bodies through one `cat-file --batch`."""
    import threading
    proc = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def feed():  # a writer THREAD: writing every id before reading deadlocks the pipe
        proc.stdin.write("".join(s + "\n" for s in shas).encode())
        proc.stdin.close()

    threading.Thread(target=feed, daemon=True).start()
    for _ in shas:
        header = proc.stdout.readline().split()
        size = int(header[2])
        body = proc.stdout.read(size)
        proc.stdout.read(1)
        yield header[0].decode(), header[1].decode(), body
    proc.wait()


def as_text(body: bytes) -> bytes:
    if body[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return body.decode("utf-16").encode("utf-8")
        except UnicodeDecodeError:
            return body
    return body


def scan(repo):
    objs = objects(repo)
    paths = path_map(repo)
    by_type = collections.Counter(t for _, t in objs)
    wanted = [s for s, t in objs if t in ("blob", "commit", "tag")]
    matches, branch_hits, scanned_bytes = [], 0, 0
    for sha, typ, body in read_all(repo, wanted):
        text = as_text(body)
        scanned_bytes += len(body)
        branch_hits += len(BRANCH_RE.findall(text))
        for name, rx in COMPILED.items():
            for m in rx.finditer(text):
                value = m.group(0)
                line_start = text.rfind(b"\n", 0, m.start()) + 1
                line_end = text.find(b"\n", m.end())
                line = text[line_start: line_end if line_end != -1 else len(text)]
                matches.append({
                    "detector": name, "object": sha, "type": typ,
                    "paths": sorted(paths.get(sha, [])) or ["<commit/tag message or unreachable>"],
                    "length": len(value), "entropy": round(entropy(value), 2),
                    "synthetic_marker_in_value": bool(SYNTHETIC_MARKERS.search(value)),
                    "synthetic_marker_on_line": bool(SYNTHETIC_MARKERS.search(line)),
                    "_value": value,          # kept IN PROCESS for de-dup only; never printed
                })
    secret_paths = sorted({p for ps in paths.values() for p in ps if SECRET_PATHS.search(p)})
    return objs, by_type, scanned_bytes, matches, branch_hits, secret_paths


def planted_values() -> dict:
    """One synthetic value per detector -- each ASSEMBLED, so no line of this
    file holds a whole one (a scan of the tree must not find the scanner)."""
    return {
        "anthropic_key": b"sk-ant-api03-" + b"Q7w" * 12,
        "openai_key": b"sk-proj-" + b"Zp4" * 10,
        "google_api_key": b"AIza" + b"Sy9" * 11 + b"Kq",
        "elevenlabs_key": b"sk_" + b"a1b2c3d4" * 6,
        "xi_api_key_value": b"xi-api-key: " + b"m3N" * 10,
        "tavily_key": b"tvly-" + b"R8t" * 10,
        "brave_key": b"BSA" + b"v5X" * 10,
        "github_token": b"ghp_" + b"H2j" * 13,
        "aws_access_key": b"AKIA" + b"J7QW3Z5X9C2V4B6N",
        "slack_token": b"xoxb-" + b"12345-67890-" + b"Lm9" * 5,
        "private_key_block": b"-----BEGIN RSA " + b"PRIVATE KEY-----",
        "env_style_assignment": b"MY_SERVICE_API_KEY=" + b"Wd6" * 8,
    }


def control(workdir: pathlib.Path):
    """POSITIVE CONTROL: plant one synthetic value per detector in a scratch repo,
    in a file later DELETED (history only) and in a commit MESSAGE, then require
    the same pipeline to find every one."""
    plant = planted_values()
    for name, value in plant.items():
        assert COMPILED[name].search(value), f"detector {name} does not fire on its own sample"
    assert BRANCH_RE.search(b"api_key"), "the branch command pattern does not fire"
    repo = workdir / "control_repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git(repo, "config", "user.email", "c@c"); git(repo, "config", "user.name", "c")
    (repo / "planted.txt").write_bytes(b"\n".join(plant.values()) + b"\n")
    (repo / ".env").write_bytes(b"X=1\n")
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "plant")
    git(repo, "rm", "-q", "planted.txt", ".env")
    git(repo, "commit", "-q", "-m", "remove; message carries " + plant["tavily_key"].decode())
    _objs, _types, _bytes, matches, _branch, secret_paths = scan(repo)
    found = {m["detector"] for m in matches}
    missing = sorted(set(plant) - found)
    in_message = any(m["type"] == "commit" and m["detector"] == "tavily_key" for m in matches)
    head_tree = git(repo, "ls-tree", "-r", "--name-only", "HEAD").decode()
    print(f"CONTROL planted={len(plant)} found={len(found & set(plant))} missing={missing} "
          f"found_in_commit_message={in_message} planted_file_absent_from_HEAD={'planted.txt' not in head_tree} "
          f"secret_path_found={'.env' in secret_paths}")
    assert not missing and in_message and ".env" in secret_paths
    print("CONTROL PASSED")


def main():
    repo, mode = pathlib.Path(sys.argv[1]), sys.argv[2]
    if mode == "control":
        control(repo)
        return
    objs, by_type, scanned_bytes, matches, branch_hits, secret_paths = scan(repo)
    print(f"objects in store={len(objs)} by type={dict(by_type)} bytes scanned={scanned_bytes}")
    print(f"branch-command keyword hits (words, not values)={branch_hits}")
    print(f"secret-shaped PATHS ever committed={len(secret_paths)} {secret_paths}")
    per = collections.Counter(m["detector"] for m in matches)
    print(f"value-detector matches={len(matches)} by detector={dict(per)}")
    distinct = {}
    for m in matches:
        distinct.setdefault((m["detector"], m["_value"]), []).append(m)
    print(f"distinct matched values={len(distinct)}")
    for i, ((det, _v), group) in enumerate(sorted(distinct.items(), key=lambda kv: kv[0][0]), 1):
        g0 = group[0]
        paths = sorted({p for m in group for p in m["paths"]})
        print(f"  #{i} detector={det} len={g0['length']} entropy={g0['entropy']} "
              f"objects={len(group)} types={sorted({m['type'] for m in group})} "
              f"marker_in_value={g0['synthetic_marker_in_value']} "
              f"marker_on_line={any(m['synthetic_marker_on_line'] for m in group)} paths={paths}")


if __name__ == "__main__":
    main()
