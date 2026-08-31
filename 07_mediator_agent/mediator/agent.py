"""
A `mediator` LlmAgent that wraps two specialists as AgentTools:

  • buyer_specialist  — reports the buyer's budget ceiling
  • seller_specialist — calls the inventory MCP server for the seller's floor

"""

import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,
)

import os

MODEL = os.environ.get("AGENT_MODEL", "openai/gpt-4o")

_REPO_ROOT = Path(__file__).resolve().parents[4]
_INVENTORY_SERVER = str(_REPO_ROOT / "m1_mcp" / "inventory_server.py")


# ─── Specialist 1: buyer_specialist ───────────────────────────────────────────

buyer_specialist = LlmAgent(
    name="buyer_specialist",
    model=MODEL,
    description=(
        "Reports the buyer's maximum budget for property purchase. "
        "Call this when you need to know the buyer's hard ceiling."
    ),
    instruction=(
        "You represent the buyer for 742 Evergreen Terrace. Their "
        "maximum budget is $460,000.\n\n"
        "When asked, respond with EXACTLY ONE sentence stating the "
        "buyer's maximum budget. Format: 'The buyer's maximum budget "
        "is $460,000.'"
    ),
)


# ─── Specialist 2: seller_specialist ──────────────────────────────────────────

seller_specialist = LlmAgent(
    name="seller_specialist",
    model=MODEL,
    description=(
        "Reports the seller's minimum acceptable price for property sales. "
        "Call this when you need to know the seller's floor. "
        "Uses real seller-side data via MCP."
    ),
    instruction=(
        "You represent the seller of 742 Evergreen Terrace.\n\n"
        "When asked for the seller's floor price, you MUST call "
        "`get_minimum_acceptable_price` with property_id="
        "'742-evergreen-austin-78701' to retrieve the real floor.\n\n"
        "Respond with EXACTLY ONE sentence. Format: 'The seller's "
        "minimum acceptable price is $X.'"
    ),
    tools=[
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=[_INVENTORY_SERVER],
                )
            )
        )
    ],
)

# ─── The mediator (the parent agent) ──────────────────────────────────────────

root_agent = LlmAgent(
    name="mediator",
    model=MODEL,
    description=(
        "Real estate negotiation mediator. Proposes fair midpoint prices "
        "by consulting both buyer-side and seller-side specialists."
    ),
    instruction=(
        "You are an impartial real estate mediator for 742 Evergreen Terrace.\n\n"
        "When asked about pricing or whether a deal is possible:\n"
        "1. Call `buyer_specialist` to learn the buyer's maximum budget.\n"
        "2. Call `seller_specialist` to learn the seller's minimum acceptable price.\n"
        "3. If buyer_max >= seller_min, propose the **midpoint** as a fair price.\n"
        "4. If buyer_max < seller_min, explain that no deal is possible — "
        "   there is no Zone of Possible Agreement.\n\n"
        "Always call BOTH specialists. Show your reasoning by citing both "
        "numbers in your final answer."
    ),
    tools=[
        AgentTool(agent=buyer_specialist),    
        AgentTool(agent=seller_specialist),
    ],
)
