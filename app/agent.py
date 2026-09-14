from strands import Agent
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel

from .lib.request_context import current_tracking, current_user_id
from .tools.laws_africa import search_laws_africa
from .tools.corpus_search import search_legal_corpus
from .tools.case_db import read_cases_db
from .tools.web_search import web_search
from .tools.docx_gen import generate_docx, fetch_writing_sample

# ---------------------------------------------------------------------------
# Tool-call tracking hook
# ---------------------------------------------------------------------------
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

tool_call_tracker = ToolCallTracker()


# ---------------------------------------------------------------------------
# Deterministic style-sample injection for drafting_agent
# --------------------------------------------------------------------------


class DraftingSampleInjector(HookProvider):
    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)

    def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use.get("name") != "drafting_agent":
            return

        tool_input = event.tool_use.get("input")
        if not isinstance(tool_input, dict):
            return

        user_id = current_user_id.get()
        sample = fetch_writing_sample(user_id) if user_id else ""
        if not sample:
            return

        original_prompt = tool_input.get("input", "")
        tool_input["input"] = (
            "STYLE REFERENCE — an excerpt from the user's own past court submission. "
            "Mirror its structure, heading conventions, and tone ONLY. Do NOT copy any "
            "names, dates, or case facts from it into the new document — use only the "
            "facts provided below for that.\n\n"
            f"{sample}\n\n"
            "---\n\n"
            f"{original_prompt}"
        )


drafting_sample_injector = DraftingSampleInjector()

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
        "the document and return the download URL.\n\n"
        "If your input begins with a 'STYLE REFERENCE' section, that is an excerpt from the user's "
        "own past court submission. Mirror its structure, heading conventions, and tone — never copy "
        "its names, dates, or case facts into the new document."
    ),
    model=BEDROCK_MODEL,
    tools=[generate_docx],
    hooks=[tool_call_tracker],
)

# ---------------------------------------------------------------------------
# Orchestrator — sub-agents are passed straight into `tools`, exactly like
# ADK's AgentTool wrapping, just without needing the explicit wrapper class.
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are Sophia, an expert Ugandan paralegal.

For conversational legal questions:
- Delegate to research_agent for case law, precedents and current news
- Delegate to case_agent when the question involves a specific client or case,
  e.g. status updates, case history, client details and so on
- Use at most 2 sub-agent calls per response
- Synthesize results into a clear, direct answer

For document drafting requests:
- Delegate to research_agent to gather legal authorities
- Delegate to case_agent if a specific client name or case number is mentioned
- Pass gathered context to drafting_agent to produce the Word document
- Return the download URL with a short summary

For simple general questions, answer directly without delegating.

Persistence of the final result is handled automatically after you respond —
you do not need to save or write anything yourself"""

root_agent = Agent(
    name="orchestrator_agent",
    description="Root orchestrator for the Sophia Ugandan paralegal assistant.",
    system_prompt=ORCHESTRATOR_PROMPT,
    model=BEDROCK_MODEL,
    tools=[research_agent, case_agent, drafting_agent],
    hooks=[tool_call_tracker, drafting_sample_injector],
)
