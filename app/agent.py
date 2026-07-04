import os
import sys
import re
import json
import datetime
from typing import AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool, McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from google.adk.workflow import Workflow, START, FunctionNode
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.genai import types

from app.config import config

# Dynamically construct absolute path to the local MCP server module
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

# Create local stdio-based MCP toolset
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[mcp_server_path],
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Specialized Sub-Agents
# ─────────────────────────────────────────────────────────────────────────────

# Portfolio Sub-Agent
portfolio_agent = LlmAgent(
    name="portfolio_agent",
    model=config.model,
    instruction=(
        "You are a specialized personal portfolio assistant for the Indian market.\n"
        "You have access to tools to fetch user portfolios and look up current market prices.\n"
        "Your task is to help the user track their holdings, current valuation, and transaction history.\n"
        "Always offload calculations or database fetching to your tools (fetch_portfolio, market_data_lookup).\n"
        "Never estimate or hallucinate financial numbers. Format your responses in clear, scannable tables.\n"
        "Always append the disclaimer: 'Calculations are for informational and agentic simulation purposes based on current regulatory frameworks. Please consult a chartered accountant for official filings.'"
    ),
    description="Resolves queries about user portfolio holdings, current valuation, and transaction history.",
    tools=[mcp_toolset]
)

# Tax Sub-Agent
tax_agent = LlmAgent(
    name="tax_agent",
    model=config.model,
    instruction=(
        "You are a specialized Indian tax compliance assistant.\n"
        "You have access to tools to calculate Short-Term (STCG) and Long-Term (LTCG) capital gains tax deterministically, and to search tax regulations/deadlines.\n"
        "Differentiate holding periods based on the FY 2024-25/FY 2025-26 rules:\n"
        "  - Listed equity/securities: STCG <= 12 months (20% rate), LTCG > 12 months (12.5% rate).\n"
        "  - Other assets (gold, unlisted shares, etc.): STCG <= 24 months (slab rate), LTCG > 24 months (12.5% rate).\n"
        "  - Debt Mutual Funds: Always treated as STCG/slab rate, no LTCG.\n"
        "Always offload tax calculations to the tax_calculator tool. Never calculate tax manually in your head.\n"
        "Search regulations using regulatory_search if you need tax rates or advance tax deadlines.\n"
        "Be concise and scannable.\n"
        "Always append the disclaimer: 'Calculations are for informational and agentic simulation purposes based on current regulatory frameworks. Please consult a chartered accountant for official filings.'"
    ),
    description="Resolves queries about capital gains tax calculations (STCG/LTCG), tax liabilities, and regulatory or advance tax deadlines.",
    tools=[mcp_toolset]
)

# Orchestrator Agent
orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction=(
        "You are the Lead Financial and Tax Concierge Orchestrator operating in the Indian financial ecosystem.\n"
        "Analyze the user's request:\n"
        "  - If it is about portfolio holdings, current valuation, or transaction history, delegate to portfolio_agent.\n"
        "  - If it is about capital gains tax calculations (STCG/LTCG), tax liabilities, or regulatory or advance tax deadlines, delegate to tax_agent.\n"
        "Always delegate to the sub-agents using your tools (AgentTool). Do not answer directly unless it is a generic greeting.\n"
        "Summarize the sub-agent's findings in a friendly, concierge-like tone, maintaining all calculated details.\n"
        "Ensure the disclaimer is appended: 'Calculations are for informational and agentic simulation purposes based on current regulatory frameworks. Please consult a chartered accountant for official filings.'"
    ),
    tools=[AgentTool(portfolio_agent), AgentTool(tax_agent)]
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Workflow Nodes & Custom Logic
# ─────────────────────────────────────────────────────────────────────────────

# Security Checkpoint Node (Phase 4 requirements)
def security_checkpoint(ctx: Context, node_input) -> Event:
    """Checks the user prompt for PII (PAN/Aadhaar) and prompt injection."""
    pan_regex = r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
    aadhaar_regex = r"\b[0-9]{4}\s?[0-9]{4}\s?[0-9]{4}\b"
    
    text = ""
    if hasattr(node_input, "parts") and node_input.parts:
        text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, str):
        text = node_input
        
    scrubbed_text = text
    pii_found = False
    
    # PII Scrubbing
    if config.pii_redaction_enabled:
        if re.search(pan_regex, text, re.IGNORECASE):
            scrubbed_text = re.sub(pan_regex, "[REDACTED PAN]", scrubbed_text, flags=re.IGNORECASE)
            pii_found = True
        if re.search(aadhaar_regex, text):
            scrubbed_text = re.sub(aadhaar_regex, "[REDACTED AADHAAR]", scrubbed_text)
            pii_found = True
            
    # Prompt Injection Detection
    injection_keywords = ["ignore previous instructions", "bypass rules", "system prompt", "override instruction", "jailbreak"]
    injection_detected = False
    if config.injection_detection_enabled:
        for kw in injection_keywords:
            if kw in text.lower():
                injection_detected = True
                break
                
    # Domain-specific rule: Any request requesting trades or modifications requires consent.
    requires_approval = False
    if any(keyword in text.lower() for keyword in ["sell all", "clear portfolio", "delete transaction", "simulate transaction", "log sale"]):
        requires_approval = True
        
    # Structured Audit Log
    audit_log = {
        "timestamp": datetime.datetime.now().isoformat(),
        "pii_detected": pii_found,
        "injection_detected": injection_detected,
        "requires_approval": requires_approval,
        "severity": "CRITICAL" if injection_detected else ("WARNING" if pii_found or requires_approval else "INFO"),
        "message": f"Processed message: PII={pii_found}, Injection={injection_detected}, ApprovalRequired={requires_approval}"
    }
    print(f"[AUDIT LOG] {json.dumps(audit_log)}")
    
    if injection_detected:
        return Event(
            route="SECURITY_EVENT",
            output="Security Violation: Potential prompt injection detected. Access denied.",
            state={"audit_log": audit_log}
        )
        
    return Event(
        route="SECURE",
        output=scrubbed_text,
        state={
            "clean_input": scrubbed_text,
            "requires_approval": requires_approval,
            "audit_log": audit_log
        }
    )

# Security Handler Node
def security_handler(node_input: str) -> Event:
    """Handles and formats security violation output."""
    warning_text = f"⚠️ Security Check Failed: {node_input}"
    return Event(
        output=warning_text,
        content=types.Content(role="model", parts=[types.Part.from_text(text=warning_text)])
    )

# Compliance Human-In-The-Loop Node (HITL)
async def compliance_approval_gate(ctx: Context, node_input) -> AsyncGenerator[Event, None]:
    """Pauses execution if the user requires compliance consent for transaction simulations."""
    requires_approval = ctx.state.get("requires_approval", False)
    if not requires_approval:
        yield Event(output=node_input)
        return
        
    # Check if we have received approval from resume_inputs
    if not ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="compliance_consent",
            message="✋ Compliance Approval Required: You are about to perform or simulate a transaction modification. Do you authorize this action? (Please type 'yes' to approve or 'no' to decline)"
        )
        return
        
    consent = ctx.resume_inputs.get("compliance_consent", "").lower().strip()
    if consent == "yes":
        ctx.state["requires_approval"] = False  # Reset flag
        yield Event(
            output=node_input,
            content=types.Content(role="model", parts=[types.Part.from_text(text="✅ Consent granted. Proceeding with the action...")])
        )
    else:
        ctx.state["requires_approval"] = False  # Reset flag
        cancel_msg = "❌ Action cancelled. Human compliance consent was not granted."
        yield Event(
            output=cancel_msg,
            content=types.Content(role="model", parts=[types.Part.from_text(text=cancel_msg)])
        )

# Final Output Node (adds structural disclaimer)
def final_output(ctx: Context, node_input) -> Event:
    """Ensures a structural disclaimer is appended to the final response."""
    text = ""
    if isinstance(node_input, str):
        text = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        text = "".join(part.text for part in node_input.parts if part.text)
    else:
        text = str(node_input)
        
    disclaimer = "Calculations are for informational and agentic simulation purposes based on current regulatory frameworks. Please consult a chartered accountant for official filings."
    if disclaimer not in text:
        text = f"{text}\n\n---\n*{disclaimer}*"
        
    return Event(
        output=text,
        content=types.Content(role="model", parts=[types.Part.from_text(text=text)])
    )

# ─────────────────────────────────────────────────────────────────────────────
# 3. Workflow Graph Construction
# ─────────────────────────────────────────────────────────────────────────────

security_checkpoint_node = FunctionNode(func=security_checkpoint, name="security_checkpoint")
security_handler_node = FunctionNode(func=security_handler, name="security_handler")
compliance_approval_gate_node = FunctionNode(
    func=compliance_approval_gate, 
    name="compliance_approval_gate", 
    rerun_on_resume=True
)
final_output_node = FunctionNode(func=final_output, name="final_output")

edges = [
    # Start goes to security checkpoint
    (START, security_checkpoint_node),
    
    # Security checkpoint routing:
    (security_checkpoint_node, {"SECURITY_EVENT": security_handler_node, "SECURE": orchestrator}),
    
    # Orchestrator goes to the approval gate
    (orchestrator, compliance_approval_gate_node),
    
    # The approval gate goes to final output formatting
    (compliance_approval_gate_node, final_output_node),
    
    # Security handler also goes to final output formatting
    (security_handler_node, final_output_node),
]

root_agent = Workflow(
    name="fin_tax_concierge_workflow",
    edges=edges,
    description="Orchestrated financial portfolio and tax compliance concierge graph.",
)

# App instance
app = App(
    root_agent=root_agent,
    name="app",  # Must match the agent directory name: "app"
    resumability_config=ResumabilityConfig(is_resumable=True)  # Enable HITL resumption
)
