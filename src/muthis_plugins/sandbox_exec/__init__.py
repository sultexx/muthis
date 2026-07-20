# sandbox_exec — isolated in-container code execution (V2 Phase 2, Milestone 1).
# The founding EXECUTION privilege (sandbox.execute). LOOK-only is untouched:
# execution lives ONLY in a throwaway container, never on the user's machine (DEC-3).

from .plugin import SandboxExecPlugin

__all__ = ["SandboxExecPlugin"]
