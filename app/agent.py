from strands import Agent
from strands.models import BedrockModel

from .tools.laws_africa import search_laws_africa
from .tools.corpus_search import search_legal_corpus
from .tools.case_db import read_cases_db
from .tools.web_search import web_search
from .tools.docx_gen import generate_docx
from .tools.supabase_writer import write_result

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
        "Searches Ugandan case law from Laws.Africa and searches the web for recent legal developments. "
        "Use for legal precedents, judgments, and research on legal topics."
    ),
    system_prompt=(
        "You are a legal research specialist. Search for relevant Ugandan judgments and "
        "search the web for recent legal developments vis-a-vis the user's query."
        "Return well-organised findings with citations."
        "CRITICAL: Only state facts, case names, dates, sentences, or holdings that appear "
        "explicitly in the tool results you received. Never infer, extrapolate, or invent "
        "case details, outcomes, or citations. If the tool results don't contain a fact "
        "you'd need to answer fully, say so explicitly rather than filling the gap."
    ),
    model=BEDROCK_MODEL,
    tools=[search_laws_africa, web_search,],
)

case_agent = Agent(
    name="case_agent",
    description=(
        "Reads the user's case database records"
        "Use when the user asks about specific clients or file numbers."
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
    tools=[read_cases_db],
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
- Finally, use the write_result tool to save the results to the database.

For document drafting requests:
- Delegate to research_agent to gather legal authorities
- Delegate to case_agent if a specific client is mentioned
- Pass gathered context to drafting_agent to produce the Word document
- Return the download URL with a short summary
- Finally, use the write_result tool to save the results to the database.

For simple general questions, answer directly without delegating."""

root_agent = Agent(
    name="orchestrator_agent",
    description="Root orchestrator for the Sophia Ugandan paralegal assistant.",
    system_prompt=ORCHESTRATOR_PROMPT,
    model=BEDROCK_MODEL,
    tools=[research_agent, case_agent, drafting_agent, write_result],
)
