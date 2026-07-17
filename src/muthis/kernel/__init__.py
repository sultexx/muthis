# src/muthis/kernel/__init__.py
"""
The SEALED KERNEL of Mut'his V2 (V2_ROADMAP.md §3.1, born in Phase 0).

Home of everything plugins may never own: the orchestrator and turn
lifecycle, the agentic loop and its cap, the HighlightGate (ONE draw per
turn — a universal invariant over ALL plugins), history hygiene, the budget
gate, verbosity, and the ToolRouter dispatch registry.

Deliberately import-free: modules are imported by their full paths
(muthis.kernel.orchestrator, …) so package init can never create an import
cycle through the V1 compat shims that still live at the old muthis.* paths
(kept until Phase 1 — Sultan's decision Q-4).
"""
