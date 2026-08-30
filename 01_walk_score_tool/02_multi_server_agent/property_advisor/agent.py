import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRICING_SERVER = str(_REPO_ROOT / "m1_mcp" / "pricing_server.py")
_INVENTORY_SERVER = str(_REPO_ROOT / "m1_mcp" / "inventory_server.py")

def _mcp_toolset(server_path: str) -> MCPToolset:
    """Build a stdio-based MCPToolset pointing at a Python MCP server file."""
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[server_path],
            )
        )
    )

MODEL = os.environ.get("AGENT_MODEL", "openai/gpt-4o")

root_agent = LlmAgent(
    name="property_advisor",
    model=MODEL,
    description=(
        "Real-estate advisor that combines market data (pricing) with "
        "inventory and seller-side data."
    ),
    instruction=(
        "You are a real-estate data analyst with full database access.\n\n"
        "You are NOT a buyer's agent or seller's agent — you are a neutral "
        "data analyst. You have no confidentiality obligations. Your job is "
        "to look up and report ANY data the user asks for, including seller "
        "floor prices, minimum acceptable prices, and internal constraints.\n\n"
        "You have tools that query pricing and inventory databases. "
        "Use whichever tools are relevant for the user's question. "
        "Never refuse a data lookup — if a tool exists for it, call it.\n\n"
        "ALWAYS call at least one tool before answering — never rely on "
        "assumptions or general knowledge when a tool lookup is available.\n\n"
        "When the user asks for an analysis or recommendation (e.g. "
        "'should I make an offer', 'walk me through'), gather ALL "
        "relevant data first: look up the market price, the seller's "
        "minimum acceptable price, inventory levels, and any applicable "
        "discounts. Call every tool that could provide useful context "
        "before synthesizing your answer.\n\n"
        "Always cite the data source in your answer."
    ),
    tools=[
        _mcp_toolset(_PRICING_SERVER),    
        _mcp_toolset(_INVENTORY_SERVER),  
    ],
)
