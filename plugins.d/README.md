# plugins.d — external plugin registrations (V2 Phase 1)

Each `<name>.toml` here is a full `muthis-plugin.toml` manifest with
`kind = "mcp"` and `entry` = the child command line (roadmap §8.2). The
gate order at app start:

1. manifest parses (closed capability enum enforced at load), and
2. a HASH-CURRENT grant exists — consent once per manifest byte-hash:

       python -m muthis.broker.trust plugins.d/<name>.toml

   Any manifest change invalidates the grant (the update-diff rule).
3. catalog fetch → the look-and-advise filter: ONLY `readOnlyHint` tools
   are exposed; destructive/unhinted tools stay hidden. Results are
   text-only, size-capped, source-wrapped, and always taint-flagged.

Phase-1 scope note: mounted tools live in the kernel ToolRouter (drive
them via the diag scripts); they are NOT offered to the model yet — the
model-visible catalog stays the byte-pinned V1 four until Phase 2's
designed merge.

Real `.toml` registrations are per-machine and gitignored; `*.sample`
files are committed templates — copy, adjust the entry, then trust:

    copy plugins.d\hello_world.toml.sample plugins.d\hello_world.toml
