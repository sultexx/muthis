# src/muthis_plugins/file_read/__init__.py
"""read_local_file as a core plugin — the fully ROUTED executor (the dogfood
proof: schema + stateless execute over a granted capability seam)."""

from .plugin import FileReadPlugin

__all__ = ["FileReadPlugin"]
