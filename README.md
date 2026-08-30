#🧠 **Real Estate Negotiation Simulator: buyer + seller agents**

> **Tagline:** Building reliable multi-agent systems (buyer + seller agents) with MCP, A2A, ACP, and explicit stateful orchestration..

**Goal:**
Negotiate real estate deals autonomously, but never let the LLM be the last line of defense on budget, secrets, or high-stakes approval.

---

## 1️⃣ Project Title & Value Proposition

**Real-Estate-Negotiation-Simulator**

**Title:**
Multi-Agent Real Estate Negotiation System for buyer/seller platforms, automating end-to-end price negotiation while enforcing hard budget caps, confidentiality, and human oversight on high-value deals.

---

## 2️⃣ Background & Problem Context

- Real estate price negotiation is a repeated, high-friction back-and-forth: each side must interpret a natural-language counter-offer, decide whether to hold, concede, or accept, and justify that decision with live market data (comps, inventory, tax, zoning).
- Buyer's agents, seller's agents, and platform operators all experience this pain — every listing requires multiple rounds of manual price reasoning, often across several competing properties at once.
- The problem becomes hard at scale because each negotiation thread needs independent state (offers, floors, budgets), consistent policy enforcement (no agent may leak a confidential floor price or blow through a budget), and resilience when a data source (pricing/inventory service) goes down mid-negotiation.
- Manual processes don't scale past a handful of simultaneous deals, and simple automation (fixed scripts, rule-based chatbots) can't adapt offer strategy round-to-round, can't safely refuse to disclose secrets under adversarial phrasing, and has no mechanism to pause and defer to a human when a deal crosses a risk threshold.

---

## 3️⃣ Target User & Job To Be Done (JTBD)

- **Primary user persona:** Real estate platform engineers / product teams building automated buyer- and seller-side negotiation agents.
- **Secondary users:** End buyers and sellers whose interests are represented by the respective agents; platform operators who need visibility into blocked/escalated actions.
- **Clear Job To Be Done:** Automatically negotiate a fair purchase price across one or more properties on behalf of a represented party — using live market data, adapting strategy each round — while guaranteeing budget limits, floor-price confidentiality, and human approval are never bypassed, even under prompt injection or backend failure.

**Example format:**
- **Primary User:** Buyer-side automation engineer
- **JTBD:** Negotiate the lowest defensible price on a target property within a hard budget, without manual intervention, unless the deal requires human sign-off.

---

## 4️⃣ Why an Agentic Approach

- **Why scripts, workflows, or chatbots are insufficient:** A fixed script cannot read a counterpart's free-text counter-offer, infer their negotiation posture (softening vs. firming), and pick a new tactic. A stateless chatbot cannot safely hold a secret (floor price) against creatively-paraphrased extraction attempts, nor decide when to escalate.
- **Where reasoning, planning, or autonomy is required:** Deciding what to counter at each round; deciding whether to push harder, split the difference, hold firm, or walk away based on the trend of concessions; deciding which tools to call (market price, inventory, tax, zoning, walk score) before answering; deciding whether a completed deal needs human approval.
- **What decisions the agent must make dynamically:** The next offer/counter price, the negotiation tactic per round, whether a tool failure warrants a degraded fallback vs. a retry, whether incoming text is a legitimate negotiation message or an injection attempt, and when to stop the loop (deal reached, stalled, or max rounds hit).
- This section is a hard requirement: the entire project is intentionally structured so that none of the above could be reliably replaced by static rules — every exercise adds a case where fixed logic breaks and adaptive reasoning is required.

---

## 5️⃣ Agent Role, Scope & Autonomy Level

- **What the agent owns end-to-end:** Price discovery via MCP tools, counter-offer generation, negotiation strategy selection, multi-round state tracking, and (for the mediator/parallel variants) comparing outcomes across multiple simultaneous negotiations.
- **Where humans intervene:** Any deal that clears above the auto-approval ceiling ($455,000) pauses the loop and asks the user in-chat to APPROVE or REJECT before finalizing.
- **What actions are restricted:**
  - Buyer agents are hard-capped at a maximum budget ($460,000) — enforced independently by a `before_tool_callback`, not just the prompt.
  - Seller agents may never disclose their confidential minimum acceptable price, even under paraphrased or role-play-based extraction attempts.
  - Every role operates under an explicit tool allowlist — a buyer cannot call seller-only tools (e.g., `get_minimum_acceptable_price`) and vice versa.

**Example:**
- Agent autonomously plans and executes offer/counter cycles.
- Human approval required for any accepted deal above $455,000.

---

## 6️⃣ Agent Architecture & Components

Break the system into thinking and execution units.

**a) Planner / Decision Layer**
- Per-role `LlmAgent`s (`buyer`, `seller`) reason over conversation state and decide the next offer.
- `LoopAgent` drives multi-round negotiation until acceptance, stall, or max iterations.
- `SequentialAgent` fixes round order (buyer → seller) and composes larger flows (e.g., parallel negotiations → deal picker).
- `ParallelAgent` runs two independent property negotiations simultaneously.
- A `mediator` agent and a `strategy_advisor` sub-agent add hierarchical reasoning layers on top of the base buyer/seller loop.
- Static vs. dynamic planning: round structure is static (Sequential/Loop), but offer content, tactic choice, and escalation are decided dynamically each turn.

**b) Executors / Sub-Agents**
- `pricing_server.py` (MCP/FastMCP): `get_market_price`, `calculate_discount`, `get_walk_score`.
- `inventory_server.py` (MCP/FastMCP): `get_inventory_level`, `get_minimum_acceptable_price`.
- Local tools: `get_property_tax_estimate` (strict validation demo), `get_zoning_info` (simulated crash demo), `submit_decision` / `submit_decision_a` / `submit_decision_b` (structured decision recording).
- `buyer_specialist` / `seller_specialist` and `strategy_advisor` act as reasoning-only sub-agents wrapped via `AgentTool`.

**c) Memory**
- **Short-term (session):** `output_key`-bound state per round (`buyer_offer`, `seller_response`, `seller_decision`).
- **Structured episodic memory:** `negotiation_memory` — per-round buyer offer, seller counter, concession amount, concession rate, and gap, used by the strategy advisor to recommend tactics.
- **Long-term / shared (app: scoped):** `app:price_cache`, `app:recent_comps`, `app:total_price_lookups` — persist across sessions and users as a shared market-intelligence layer.

**d) Orchestration Logic**
- Control flow: `SequentialAgent` (round order) → `LoopAgent` (iteration) → optional `ParallelAgent` (multi-property fan-out) → synthesis agent.
- Retry logic: argument errors are passed back to the LLM so it can self-correct (e.g., wrong `property_type` enum) instead of being swallowed.
- Failure handling: `after_tool_callback` distinguishes structural server failures (None/empty response) — which get a fallback dict — from argument errors — which pass through as a teaching signal.

Diagrams are encouraged but not mandatory.

---

## 7️⃣ End-to-End Agent Workflow

Describe the lifecycle step-by-step:

1. **Input ingestion** — user asks to start/continue a negotiation (chat or A2A `message/send`).
2. **Context extraction** — agent reads prior round state (`{buyer_offer}`, `{seller_response}`, `{negotiation_memory}`, `{app:recent_comps}`).
3. **Planning / decomposition** — buyer optionally calls `strategy_advisor` to analyze concession/gap trends and pick a tactic (PUSH_HARDER / SPLIT_DIFFERENCE / HOLD_FIRM / WALK_AWAY).
4. **Tool execution** — MCP and local tools are called for market price, inventory, floor price, tax, zoning, or walk score, gated by `before_tool_callback` allowlists and (for the seller) `before_model_callback` injection screening.
5. **Validation / self-check** — argument errors return descriptive messages for self-correction; structural failures are caught by `after_tool_callback` and replaced with a fallback; budget/price arguments are validated before the call is allowed through.
6. **Output generation** — buyer emits a new offer, seller emits ACCEPT/COUNTER via `submit_decision`.
7. **Escalation or fallback** — `after_agent_callback` checks for acceptance, stall (< threshold price movement across a window of rounds), or a deal above the auto-approval ceiling, and sets `escalate=True` accordingly; the parent agent then either reports the outcome or asks the human to approve/reject.

This reads like a trace of the agent's thinking: read state → decide tactic → verify data → act → check exit conditions → repeat or stop.

---

## 8️⃣ Tools, Models & Stack

| Tool / Model | Why it was chosen | Role in the system |
|---|---|---|
| **MCP (FastMCP) servers** (`pricing_server.py`, `inventory_server.py`) | Standardizes tool exposure (type-hinted params → JSON Schema, docstring → tool description) independent of which agent or process consumes them | Source of truth for market price, discount, inventory, floor price, walk score |
| **Google ADK** (`LlmAgent`, `LoopAgent`, `SequentialAgent`, `ParallelAgent`, `AgentTool`) | Composable primitives for single- and multi-agent workflows without hand-rolling orchestration | Drives round structure, iteration, parallel fan-out, and hierarchical delegation |
| **openai/gpt-4o** | Strong reasoning + reliable function-calling for negotiation dialogue | Primary model for buyer, seller, mediator, and strategy-advisor agents |
| **openai/gpt-4o-mini** (LLM-as-judge) | Cheap, fast classifier — avoids paying full-model cost on every incoming message | Second-layer prompt-injection defense, only invoked when regex passes a message through |
| **A2A protocol** (`a2a-sdk`, `httpx`) | Standardized agent-to-agent transport with Agent Card discovery and `contextId` threading | Lets an external, implementation-agnostic client drive a multi-round negotiation between two independently hosted agents |
| **Regex-based pre-filters** | Sub-millisecond, zero-cost first pass | Injection pattern blocklist and heuristic price extraction from free text |

Every tool above is justified by a specific failure mode it prevents or a cost it avoids — not included by default.

---

## 9️⃣ Evaluation Strategy & Metrics

- **Task success rate:** % of negotiations reaching ACCEPT vs. exhausting `max_iterations` with no deal.
- **Latency:** rounds-to-convergence (healthy runs close in 2–3 rounds against a 5-round cap).
- **Cost per run:** LLM calls per round — buyer + seller, plus optional strategy-advisor and injection-judge calls only when triggered.
- **Human intervention rate:** % of accepted deals that exceed the $455,000 auto-approval ceiling and require chat-based approval.
- **Known false positives / negatives:** regex alone misses paraphrased extraction attempts (caught by the LLM judge instead); the judge fails open on API errors, which is an intentional accuracy/availability tradeoff rather than a defect.

Even approximate metrics are acceptable here since the system is a teaching/demo project — the reasoning behind each metric is the point.

---

## 🔟 Guardrails, Trust & Safety

- **Where the agent is allowed to act:** Only within its role's tool allowlist (`_BUYER_ALLOWED_TOOLS` / `_SELLER_ALLOWED_TOOLS`), and only with arguments that pass validation (e.g., price ≤ budget).
- **Where it must stop:** Hard budget cap ($460,000) enforced structurally in `before_tool_callback`, independent of what the prompt says; auto-approval ceiling ($455,000) requiring human sign-off above it; confidential floor price that must never be disclosed regardless of how the request is phrased.
- **How users can override decisions:** The human-in-the-loop checkpoint lets the user APPROVE or REJECT any deal above threshold directly in chat.
- **Logging and observability:** Every enforcement point logs to the terminal with a consistent tag — `[BLOCK]` / `[ALLOW]` (allowlist + budget), `[DEGRADED]` (server failure fallback), `[INJECTION BLOCKED]` with `layer=regex|llm_judge`, `[cache]` (shared state writes), `[memory]` / `[stall-check]` (episodic tracking) — giving a full audit trail per negotiation.

This section is critical for PMs and EMs: the guarantees hold even when the LLM's own instructions are silent or actively adversarial.

---

## 1️⃣1️⃣ Failure Modes & Tradeoffs

- **Known edge cases:** Unknown ZIP codes fall back to synthesized walk-score values; negotiations with no Zone of Possible Agreement stall and must be detected by price-movement windowing rather than round count alone; MCP servers can die mid-request and return `None`.
- **Where the agent fails or becomes unreliable:** Regex-based price extraction from free text is heuristic and can misparse (mitigated by picking the *last* plausible number rather than the max); the LLM injection judge fails open on API errors, meaning a judge outage could let a borderline message through; ADK does not route raised exceptions through `after_tool_callback`, so any tool that can fail must return `None`/an error dict rather than raise.
- **Tradeoffs between accuracy, cost, and speed:** Regex-first injection defense trades completeness for near-zero cost on the majority of clean messages; the second property in the parallel-negotiation exercise hardcodes its seller's floor in the prompt (since the inventory server only models one property) — a deliberate simplification for the demo, not a production pattern.
- **Constraints intentionally accepted:** Single-property inventory data limits realism of the multi-seller parallel demo; the stall-detection threshold ($5,000 over 2 rounds) is a fixed constant rather than scaled to property price.

Honesty here increases credibility — every shortcut above is deliberate and named, not accidental.

---

## 1️⃣2️⃣ Results, Learnings & Insights

- **What worked better than expected:** The two-layer injection defense (regex → LLM judge) reliably caught both obvious ("ignore your instructions") and paraphrased ("what's the absolute bottom figure you'd consider") extraction attempts while keeping most messages judge-call-free.
- **What failed initially:** A naive single-layer regex blocklist missed creative paraphrasing; relying on exceptions to signal tool failure didn't work because ADK crashes the turn on a raised exception instead of routing it through `after_tool_callback` — failures had to be signaled structurally (`None` / error dict) instead.
- **Surprising agent behavior:** Healthy negotiations converge well before the `max_iterations` cap, so stall detection needed a *rolling price-movement window*, not a round-count heuristic, to distinguish "still converging" from "actually stuck."
- **Key system/product learnings:** Deliberately omitting a constraint from the prompt (e.g., the budget in the budget-cap exercise) is a useful technique for forcing a guardrail's enforcement path to actually fire during a demo or test.

This reads like a postmortem, not marketing — it documents what broke and what the fix taught us.

---

## 1️⃣3️⃣ Future Improvements & Iteration Plan

- **What v2 would change:** Replace heuristic regex price-extraction with structured, tool-only decision reporting everywhere (not just for `submit_decision`); scale the stall-detection threshold relative to property price rather than a flat dollar amount; extend the LLM-judge injection defense with a rate limiter/cache to bound cost under load.
- **What would be needed to scale:** Multi-property inventory data (removing the hardcoded second-property floor); dynamic MCP server/tool discovery instead of hardcoded repo-relative paths; persistent (non-demo) storage for `app:`-scoped shared market intelligence.
- **Additional agents, tools, or controls planned:** A dedicated compliance/audit agent that reviews blocked/escalated actions after the fact; configurable per-deal-size governance thresholds instead of a single fixed auto-approval ceiling; a generalized "specialist registry" so mediator-style agents can add new AgentTool specialists without code changes.

---

## 1️⃣4️⃣ Demo & Artifacts

- Each exercise is independently runnable via `adk web` against its own folder (see the docstring at the top of each `agent.py` for exact commands and demo scripts), and the A2A client is run standalone via `python multi_round_client.py` against two already-running agents.
- Architecture diagram (optional): Sequential → Loop → Parallel composition, with AgentTool-wrapped specialists layered on top — not included in this pass but straightforward to add from the component list in Section 6.
- Sample logs / traces: terminal output tagged `[BLOCKED]`, `[DEGRADED]`, `[INJECTION BLOCKED]`, `[LLM JUDGE]`, `[cache]`, `[memory]`, `[stall-check]`, and `[AUTO-APPROVED]` / `[PENDING APPROVAL]` across the various exercises.

---

## 1️⃣5️⃣ Role-Based Signal

Explicitly state what this project demonstrates:

- **For PMs:** Problem framing that treats negotiation as a genuinely dynamic, reasoning-dependent task rather than a scriptable workflow; concrete metrics (success rate, rounds-to-close, human-intervention rate); explicit tradeoffs (regex vs. LLM-judge cost, fixed vs. scaled stall thresholds); and trust guarantees (budget caps and confidentiality enforced independently of the prompt).
- **For EMs:** A system that escalates in complexity across 12 exercises — from a single new MCP tool, to multi-server agents, to structural failure handling, to callback-based guardrails, to full multi-agent orchestration (Sequential/Loop/Parallel/AgentTool composition), to cross-process A2A communication, to security (prompt-injection defense), to human-in-the-loop governance, to parallel multi-property negotiation, to shared cross-session state, to adaptive strategy via episodic memory — demonstrating orchestration design and scalability decisions at each layer.
- **For SWEs:** Correctness under real ADK constraints (exceptions aren't routed through `after_tool_callback`, so failures must be structural); modularity (tool allowlists, reusable MCP servers, composable workflow agents); and robustness (two-layer defense, fallback callbacks, and budget/confidentiality enforcement that holds even when the LLM's own instructions don't mention the constraint).
