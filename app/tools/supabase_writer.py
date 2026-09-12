import traceback
from strands import tool, ToolContext
from ..lib.supabase_client import get_supabase


@tool(context=True)
def write_result(prompt: str, reply: str, tool_context: ToolContext, tools_used: list[str] = []) -> str:
    """Write the final results of a completed task to Supabase.
    Call this at the end of every response to persist the output.

    Args:
        prompt: The original user prompt
        reply: The final reply text to persist
        tools_used: Names of tools used to produce the reply
    """
    run_id: str = tool_context.invocation_state.get("run_id")
    user_id: str = tool_context.invocation_state.get("user_id")
    supabase = get_supabase()
    try:
        supabase.table("task_results").upsert({
            "run_id": run_id,
            "user_id": user_id,
            "prompt": prompt,
            "status": "completed",
            "output": {"reply": reply, "toolsUsed": tools_used},
        }).execute()
        return "Successfully wrote results to Supabase."
    except Exception:
        error_detail = traceback.format_exc()
        supabase.table("task_results").upsert({
            "run_id": run_id,
            "user_id": user_id,
            "prompt": prompt,
            "status": "failed",
            "output": {"error": error_detail},
        }).execute()
        return f"Failed to write results to Supabase: {error_detail}"
