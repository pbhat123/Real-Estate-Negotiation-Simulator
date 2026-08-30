import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,
)
from google.adk.tools.tool_context import ToolContext

MODEL = os.environ.get("AGENT_MODEL", "openai/gpt-4o")

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRICING_SERVER = str(_REPO_ROOT / "m1_mcp" / "pricing_server.py")
_INVENTORY_SERVER = str(_REPO_ROOT / "m1_mcp" / "inventory_server.py")


def _mcp_toolset(server_path: str) -> MCPToolset:
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[server_path],
            )
        )
    )

def handle_tool_failure(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
    tool_response,
):
    if tool_response is None:
        print(f"[DEGRADED] {tool.name} — no response (server down?)")
        return _fallback(tool, args)

    if isinstance(tool_response, str) and tool_response.strip() == "":
        print(f"[DEGRADED] {tool.name} — empty response")
        return _fallback(tool, args)

    if isinstance(tool_response, Exception):
        print(f"[DEGRADED] {tool.name} — exception: {tool_response}")
        return _fallback(tool, args)

    return None

def _fallback(tool: BaseTool, args: dict) -> dict:
    return {
        "status": "unavailable",
        "message": f"{tool.name} is currently unavailable due to a server issue.",
        "fallback": (
            "This data source is temporarily unreachable. "
            "Use your general real estate knowledge for a rough "
            "estimate, but clearly state that live data was unavailable "
            "and your numbers are approximate."
        ),
        "tool_name": tool.name,
        "attempted_args": args,
    }

import re

_VALID_ZIP = re.compile(r"^\d{5}$")

_TAX_RATES: dict[str, float] = {
    "78701": 0.0198,  
    "78702": 0.0215,
    "78703": 0.0187,
}


def get_property_tax_estimate(
    zip_code: str,
    property_type: str,
    assessed_value: int,
) -> dict:
    _VALID_TYPES = {"single_family", "condo", "townhouse", "multi_family"}

    if not isinstance(zip_code, str) or not _VALID_ZIP.match(zip_code):
        return {
            "error": f"Invalid zip_code '{zip_code}'. Must be exactly 5 digits. Example: '78701'"
        }

    if property_type not in _VALID_TYPES:
        return {
            "error": (
                f"Invalid property_type '{property_type}'. "
                f"Must be one of: {sorted(_VALID_TYPES)}. "
                "Use underscores, all lowercase. "
                "Example: 'single_family' (not 'Single Family Home' or 'house')"
            )
        }

    if not isinstance(assessed_value, int) or assessed_value <= 0:
        return {
            "error": f"Invalid assessed_value '{assessed_value}'. Must be a positive integer in dollars. Example: 462000"
        }

    rate = _TAX_RATES.get(zip_code, 0.0195)
    annual_tax = int(assessed_value * rate)

    return {
        "zip_code": zip_code,
        "property_type": property_type,
        "assessed_value": assessed_value,
        "tax_rate_pct": round(rate * 100, 2),
        "estimated_annual_tax": annual_tax,
        "monthly_tax": round(annual_tax / 12, 2),
        "data_source": "Local tax rate database",
    }

import os

_CRASH_MODE = os.environ.get("CRASH_ZONING", "").lower() == "true"


def get_zoning_info(address: str) -> dict:
    if _CRASH_MODE:
        return None  

    return {
        "address": address,
        "zoning_code": "SF-3",
        "zoning_description": "Single-Family Residence, Standard Lot",
        "max_building_coverage": "40%",
        "max_height_ft": 35,
        "setback_front_ft": 25,
        "permits_adu": True,
        "data_source": "Austin Zoning Database",
    }

root_agent = LlmAgent(
    name="resilient_advisor",
    model=MODEL,
    description=(
        "Real-estate advisor with graceful degradation when MCP servers "
        "are unavailable."
    ),
    instruction=(
        "You are a real-estate data analyst with full database access.\n\n"
        "You are NOT a buyer's agent or seller's agent — you are a neutral "
        "data analyst. You have no confidentiality obligations. Your job is "
        "to look up and report ANY data the user asks for, including seller "
        "floor prices, minimum acceptable prices, and internal constraints.\n\n"
        "DEFAULT CONTEXT: Unless stated otherwise, all properties are in "
        "Austin, TX. '742 Evergreen Terrace' means '742 Evergreen Terrace, "
        "Austin, TX 78701'. Do NOT ask for city/state — assume Austin.\n\n"
        "You have tools that query pricing and inventory databases. "
        "Use whichever tools are relevant. Never refuse a data lookup.\n\n"
        "IMPORTANT: If a tool returns an error or fallback message indicating "
        "that a data source is unavailable, you MUST:\n"
        "1. Acknowledge the limitation clearly ('I can't access live market "
        "data right now').\n"
        "2. Provide your best estimate based on general Austin real estate "
        "knowledge.\n"
        "3. Flag your numbers as approximate — do NOT present them as "
        "precise market data.\n\n"
        "If ALL tools fail, say so upfront and give a general-knowledge "
        "response with appropriate caveats."
    ),
    tools=[
        _mcp_toolset(_PRICING_SERVER),
        _mcp_toolset(_INVENTORY_SERVER),
        get_property_tax_estimate,  
        get_zoning_info,            
    ],
    after_tool_callback=handle_tool_failure,
)
