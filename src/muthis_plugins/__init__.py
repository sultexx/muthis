# src/muthis_plugins/__init__.py
"""
muthis_plugins — the FIRST-PARTY NATIVE core plugins (V2 Phase 0, decision Q-2).

The four V1 tools re-founded as real muthis-sdk consumers — the dogfood proof
of roadmap §3.1: "if our interface cannot carry our own tools, it will not
carry anyone else's". Each package is one plugin: a muthis-plugin.toml
manifest + a ToolPlugin subclass + the V1 tool schema moved here VERBATIM
(the model-visible bytes are pinned by tests/snapshots/look_tools_v1.json).

LAYERING LAW (enforced by tests/test_core_plugins.py): this package imports
muthis_sdk and the stdlib ONLY — never muthis.*. The kernel reaches DOWN to
mount these plugins at its documented composition point
(kernel.core_router.build_core_router); nothing here reaches up.

Execution split (conflict ruling C-1): file_read executes through the router
via ctx.files; look_pointer / look_shapes / screen_refresh are DECLARATION
plugins — their execution never leaves the kernel (draw circuit + frame
lifecycle), so their descriptors carry kernel_serviced=True and their
execute() is a polite refusal that production never reaches.

Out-of-process first-party plugins (sandbox_exec, web_research, doc_rag)
arrive in Phase 2 under the top-level plugins/ tree — not here.
"""
