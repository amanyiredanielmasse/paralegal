from strands import Agent
from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel

from .lib.request_context import current_tracking
from .tools.laws_africa import search_laws_africa
from .tools.corpus_search import search_legal_corpus
from .tools.case_db import read_cases_db
from .tools.web_search import web_search
from .tools.docx_gen import generate_docx

# ---------------------------------------------------------------------------
# Tool-call tracking hook
# ---------------------------------------------------------------------------
# Registered on every agent below (orchestrator + all sub-agents) so it sees
# tool calls at every level of the delegation tree, e.g. search_laws_africa
# firing *inside* research_agent, not just research_agent itself being called
# as a tool by the orchestrator.
#
# NOTE: this reads/writes lib.request_context.current_tracking (a ContextVar),
# NOT event.invocation_state. Strands' _AgentAsTool wrapper does not forward
# invocation_state to sub-agents (it calls self._agent.stream_async(prompt, ...)
# with no invocation_state kwarg at all), so a hook relying on invocation_state
# would only ever see the outer agent's own tool calls, never what happens
# inside research_agent/case_agent/drafting_agent. contextvars propagate
# correctly through the plain `await` chain _AgentAsTool uses instead.


class ToolCallTracker(HookProvider):
    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)

    def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
        tracking = current_tracking.get()
        if tracking is None:
            return

        tool_name = event.selected_tool.tool_name if event.selected_tool else event.tool_use.get("name")
        if tool_name:
            tracking.tools_used.add(tool_name)

        if tool_name == "generate_docx" and event.result is not None:
            for block in event.result.get("content", []):
                text = block.get("text")
                if text:
                    tracking.download_url = text
                    break


# Single shared instance — HookProvider itself holds no per-request state,
# all mutable state lives in each request's invocation_state dict, so one
# instance is safely reusable across every agent and every concurrent request.
tool_call_tracker = ToolCallTracker()

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
# Swap for whatever Bedrock model your AWS account has access to.
# BedrockModel reads AWS credentials the standard way (env vars, profile, IAM role).
BEDROCK_MODEL = BedrockModel(
    model_id="deepseek.v3-v1:0",
    region_name="eu-north-1",
    strict_tools=True,
)

# ---------------------------------------------------------------------------
# Sub-agents
# ---------------------------------------------------------------------------

research_agent = Agent(
    name="research_agent",
    description=(
        "Searches Ugandan case law from Laws.Africa and the web for current legal developments. "
        "Use for legal precedents, judgments, and research on legal topics."
    ),
    system_prompt=(
        "You are a legal research specialist. Search for relevant Ugandan judgments and "
        "the user's private legal corpus to find case law, precedents, and legal authorities. "
        "Return well-organised findings with citations."
        "CRITICAL: Only state facts, case names, dates, sentences, or holdings that appear "
        "explicitly in the tool results you received. Never infer, extrapolate, or invent "
        "case details, outcomes, or citations. If the tool results don't contain a fact "
        "you'd need to answer fully, say so explicitly rather than filling the gap."
    ),
    model=BEDROCK_MODEL,
    tools=[search_laws_africa, web_search],
    hooks=[tool_call_tracker],
)

case_agent = Agent(
    name="case_agent",
    description=(
        "Reads the user's case database records and user's private legal corpus. "
        "Use when the user asks about specific clients, file numbers, or cases."
    ),
    system_prompt=(
        "You are a case management specialist. Look up the user's case records "
        "for developments relevant to the query. Return clear, factual summaries.\n\n"
        "CRITICAL: Only state facts, case names, dates, sentences, or holdings that appear "
        "explicitly in the tool results you received. Never infer, extrapolate, or invent "
        "case details, outcomes, or citations. If the tool results don't contain a fact "
        "you'd need to answer fully, say so explicitly rather than filling the gap."
    ),
    model=BEDROCK_MODEL,
    tools=[read_cases_db, search_legal_corpus],
    hooks=[tool_call_tracker],
)

drafting_agent = Agent(
    name="drafting_agent",
    description=(
        "Drafts formal Ugandan court submissions in proper legal format and produces a Word document. "
        "Only call when the user explicitly wants a document drafted."
    ),
    system_prompt=(
        "You are an expert Ugandan legal drafter. Using the context provided, produce a complete, "
        "formal court submission in proper Ugandan court format. Write in clear legal English with "
        "proper headings, citations, and a prayers/relief section. Then call generate_docx to save "
        "the document and return the download URL."
    ),
    model=BEDROCK_MODEL,
    tools=[generate_docx],
    hooks=[tool_call_tracker],
)

# ---------------------------------------------------------------------------
# Orchestrator — sub-agents are passed straight into `tools`, exactly like
# ADK's AgentTool wrapping, just without needing the explicit wrapper class.
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are Sophia, an expert Ugandan paralegal assistant.

For conversational legal questions:
- Delegate to research_agent for case law and precedents
- Delegate to case_agent for specific client cases or current news
- Use at most 2 sub-agent calls per response
- Synthesize results into a clear direct answer

For document drafting requests:
- Delegate to research_agent to gather legal authorities
- Delegate to case_agent if a specific client is mentioned
- Pass gathered context to drafting_agent to produce the Word document
- Return the download URL with a short summary

For simple general questions, answer directly without delegating.

Persistence of the final result is handled automatically after you respond —
you do not need to save or write anything yourself."""

root_agent = Agent(
    name="orchestrator_agent",
    description="Root orchestrator for the Sophia Ugandan paralegal assistant.",
    system_prompt=ORCHESTRATOR_PROMPT,
    model=BEDROCK_MODEL,
    tools=[research_agent, case_agent, drafting_agent],
    hooks=[tool_call_tracker],
)
