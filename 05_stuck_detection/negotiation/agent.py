import os
import re
import sys
from pathlib import Path

from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
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


STALL_WINDOW = 2        
STALL_THRESHOLD = 5_000 

_BUYER_ALLOWED_TOOLS = {"get_market_price", "calculate_discount"}
_SELLER_ALLOWED_TOOLS = {
    "get_market_price",
    "calculate_discount",
    "get_inventory_level",
    "get_minimum_acceptable_price",
    "submit_decision",
}

def _enforce_buyer_allowlist(tool: BaseTool, args: dict, tool_context: ToolContext):
    if tool.name not in _BUYER_ALLOWED_TOOLS:
        return {"error": f"tool '{tool.name}' is not authorized for the buyer"}
    return None

def _enforce_seller_allowlist(tool: BaseTool, args: dict, tool_context: ToolContext):
    if tool.name not in _SELLER_ALLOWED_TOOLS:
        return {"error": f"tool '{tool.name}' is not authorized for the seller"}
    return None

def submit_decision(action: str, price: int, tool_context: ToolContext) -> dict:
    """Submit the seller's decision for this round.

    Args:
        action: Exactly "ACCEPT" or "COUNTER".
        price: The price in dollars.
    """
    action_upper = action.strip().upper()
    if action_upper not in ("ACCEPT", "COUNTER"):
        return {"error": f"action must be ACCEPT or COUNTER, got: {action}"}
    tool_context.state["seller_decision"] = {"action": action_upper, "price": price}
    return {"recorded": action_upper, "price": price}

_PRICE_RE = re.compile(r"\$?(\d{3,}(?:[,.\s]\d{3})*)")

def _extract_buyer_offer_price(buyer_text: str) -> int | None:
    if not isinstance(buyer_text, str):
        return None
    candidates = []
    for match in _PRICE_RE.finditer(buyer_text):
        raw = match.group(1).replace(",", "").replace(" ", "").replace(".", "")
        try:
            n = int(raw)
        except ValueError:
            continue
        if 100_000 <= n <= 1_000_000:
            candidates.append(n)
    return max(candidates) if candidates else None

def _track_and_check_stall(callback_context: CallbackContext):
    state = callback_context.state

    decision = state.get("seller_decision")
    if isinstance(decision, dict) and decision.get("action") == "ACCEPT":
        callback_context.actions.escalate = True
        return None

    buyer_price = _extract_buyer_offer_price(state.get("buyer_offer", ""))
    seller_price = decision.get("price") if isinstance(decision, dict) else None

    history = list(state.get("offer_history", []))
    history.append({"buyer": buyer_price, "seller": seller_price})
    state["offer_history"] = history

    print(
        f"[stall-check] round {len(history)}: buyer={buyer_price} "
        f"seller={seller_price}"
    )

    if len(history) >= STALL_WINDOW:
        window = history[-STALL_WINDOW:]
        if all(r["buyer"] is not None and r["seller"] is not None for r in window):
            buyer_movements = [
                abs(window[i]["buyer"] - window[i - 1]["buyer"])
                for i in range(1, len(window))
            ]
            seller_movements = [
                abs(window[i]["seller"] - window[i - 1]["seller"])
                for i in range(1, len(window))
            ]
            max_move = max(buyer_movements + seller_movements)

            if max_move < STALL_THRESHOLD:
                state["stall_reason"] = (
                    f"No-progress detected: last {STALL_WINDOW} rounds had "
                    f"max movement of ${max_move:,} "
                    f"(threshold ${STALL_THRESHOLD:,})"
                )
                print(f"[stall-check] STALL DETECTED — {state['stall_reason']}")
                callback_context.actions.escalate = True

    return None

def _init_round_state(callback_context: CallbackContext):
    if "seller_response" not in callback_context.state:
        callback_context.state["seller_response"] = "(No seller response yet — round 1)"
    return None

_STALL_DEMO = os.environ.get("STALL_DEMO", "").lower() == "true"
_BUYER_BUDGET = 440_000 if _STALL_DEMO else 460_000
_BUYER_TARGET_LO = _BUYER_BUDGET - 10_000
_BUYER_TARGET_HI = _BUYER_BUDGET

buyer = LlmAgent(
    name="buyer",
    model=MODEL,
    instruction=(
        "You are a buyer agent for 742 Evergreen Terrace, Austin TX 78701 "
        "(listed at $485,000).\n\n"
        f"BUDGET: ${_BUYER_BUDGET:,} maximum.\n"
        f"TARGET: ${_BUYER_TARGET_LO:,} - ${_BUYER_TARGET_HI:,}.\n\n"
        "Read {seller_response}. Make your next offer with one specific dollar "
        "amount. Use your MCP pricing tools to justify it.\n\n"
        f"If you've already pushed to your max (${_BUYER_BUDGET:,}) and the seller is "
        "above it, repeat your max offer firmly."
    ),
    tools=[
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable, args=[_PRICING_SERVER],
                )
            )
        )
    ],
    before_tool_callback=_enforce_buyer_allowlist,
    output_key="buyer_offer",
    before_agent_callback=_init_round_state,
)

seller = LlmAgent(
    name="seller",
    model=MODEL,
    instruction=(
        "You are the seller agent for 742 Evergreen Terrace.\n\n"
        "Read {buyer_offer}. Look up your floor with `get_minimum_acceptable_price` "
        "for property_id='742-evergreen-austin-78701'.\n\n"
        "If buyer offer >= floor → submit_decision(action='ACCEPT', price=buyer_price).\n"
        "Else → counter-offer at a price between buyer_price and your previous counter, "
        "and submit_decision(action='COUNTER', price=your_counter).\n\n"
        "ALWAYS call submit_decision. Do not just write your decision in prose."
    ),
    tools=[
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable, args=[_PRICING_SERVER],
                )
            )
        ),
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable, args=[_INVENTORY_SERVER],
                )
            )
        ),
        submit_decision,
    ],
    before_tool_callback=_enforce_seller_allowlist,
    output_key="seller_response",
    after_agent_callback=_track_and_check_stall,  
)

negotiation_round = SequentialAgent(name="round", sub_agents=[buyer, seller])

root_agent = LoopAgent(
    name="negotiation",
    description="Multi-round buyer ↔ seller negotiation with stall detection.",
    sub_agents=[negotiation_round],
    max_iterations=5,
)
