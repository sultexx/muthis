# src/muthis_plugins/navigator_verify/plugin.py
"""NavigatorVerifyPlugin — the third mode verb, DECLARED here and SERVICED by
the kernel (DEC-73's ruling, exactly as the other two are).

WHY A SEPARATE PACKAGE FOR ONE DESCRIPTOR — SULTAN'S RULING, AND IT IS ABOUT
WHAT THE OLDER TESTS BUILD. Every catalog pin in this project builds its
catalogue through a helper that mounts a FIXED set of plugins in production
order, and the v7 helper already mounts `NavigatorPlugin`. A third descriptor
added THERE would make `_v7_router()` produce twelve tools, and both v7-era pins
would go red for a reason that has nothing to do with what they protect. The
alternative — re-basing those pins to compare snapshot file against snapshot
file — changes what they ASSERT, and they exist to catch exactly the class of
change v8 is. A separate mount keeps each pin's object matched to its era: v7's
pin keeps testing v7's catalogue and v8's tests v8's, no pin is weakened and no
claim is re-scoped.

kernel_serviced: the state this verb informs is the KERNEL'S — the step pointer
and, at Gate 2B, the verification state. A plugin holding it would make "the
result is proven" a PLUGIN'S CLAIM, which is what DEC-65 removed. So this
package contributes ONE schema and nothing else: no state, no transition, no
note, and no judgement. `execute` is unreachable in production and returns the
same refusal every declaration plugin returns.
"""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from ..common import KERNEL_SERVICED_AR
from .schema import NAVIGATOR_VERIFY_SCHEMA


class NavigatorVerifyPlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="verify",
                schema=NAVIGATOR_VERIFY_SCHEMA,
                read_only=True,
                kernel_serviced=True,
            ),
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        return ToolResult(text_ar=KERNEL_SERVICED_AR, is_error=True)
