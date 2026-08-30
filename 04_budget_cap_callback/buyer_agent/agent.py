import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,
)
from google.adk.tools.tool_context import ToolContext

BUYER_BUDGET = 460_000  

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRICING_SERVER = str(_REPO_ROOT / "m1_mcp" / "pricing_server.py")

_ALLOWED_TOOLS = {
    "get_market_price",
    "calculate_discount",
    "submit_decision",
}

def submit_decision(
    action: str, price: int, tool_context: ToolContext
) -> dict:
    action_upper = action.strip().upper()
    if action_upper not in ("OFFER", "WALK_AWAY"):
        return {"error": f"action must be OFFER or WALK_AWAY, got: {action}"}
    tool_context.state["buyer_decision"] = {
        "action": action_upper,
        "price": price,
    }
    return {"recorded": action_upper, "price": price}

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def buyer_guard(
    tool: BaseTool, args: dict, tool_context: ToolContext
):
    print(f"[{_ts()}] CALL  {tool.name}({args})")

    if tool.name not in _ALLOWED_TOOLS:
        print(f"[{_ts()}] BLOCK unauthorized tool: {tool.name}")
        return {"error": f"tool '{tool.name}' is not authorized for the buyer"}

    if tool.name == "submit_decision":
        price = args.get("price")
        if isinstance(price, (int, float)) and price > BUYER_BUDGET:
            print(
                f"[{_ts()}] BLOCK price ${price:,} exceeds budget ${BUYER_BUDGET:,}"
            )
            return {
                "error": (
                    f"price ${price:,} exceeds buyer budget of "
                    f"${BUYER_BUDGET:,}. Submit an offer at or below "
                    f"${BUYER_BUDGET:,}."
                )
            }

    print(f"[{_ts()}] ALLOW")
    return None

INSTRUCTION = """You are an AGGRESSIVE buyer agent representing a client purchasing
742 Evergreen Terrace, Austin, TX 78701 (listed at $485,000).

STRATEGY:
- Match the seller's energy. If they counter high, you counter high.
- Use your MCP pricing tools to justify offers with comps.
- When pressed, go as high as needed to close the deal.
- ALWAYS submit your decision via `submit_decision(action="OFFER", price=X)`.

When ready to commit, call `submit_decision`. Don't just write your offer
in prose — call the tool.

IMPORTANT: If a tool call is rejected because the price exceeds the budget,
immediately retry with the maximum allowed price. Do NOT ask the user to
adjust the budget — just submit at the cap."""


MODEL = os.environ.get("AGENT_MODEL", "openai/gpt-4o")

root_agent = LlmAgent(
    name="buyer_agent",
    model=MODEL,
    description="Aggressive buyer agent with budget-cap enforcement.",
    instruction=INSTRUCTION,
    tools=[
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=[_PRICING_SERVER],
                )
            )
        ),
        submit_decision,
    ],
    before_tool_callback=buyer_guard,  
)
