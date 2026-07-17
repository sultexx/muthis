# src/muthis_plugins/common.py
"""Shared Arabic surfaces of the core plugins (single-sourced against drift)."""

# The declaration-only plugins' execute() refusal. Production never reaches it:
# the kernel intercepts draw tools before the router and the router refuses
# kernel_serviced descriptors itself — this is the last defensive wall, and
# what the conformance kit's golden run observes for these plugins.
KERNEL_SERVICED_AR = "هذه الأداة تخدمها النواة مباشرة، لا هذا المسار."

# file_read's degradation when the perceive.files.read seam is absent from the
# context (the kit's bare fake kernel). The PRODUCTION no-seam path never gets
# here — kernel.tool_router rules it first with the V1 note from file_reader.py.
FILES_CAPABILITY_ABSENT_AR = "قراءة الملفات غير متاحة في هذه الجلسة."
