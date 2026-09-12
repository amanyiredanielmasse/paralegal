import traceback
from ..lib.supabase_client import get_supabase


def write_result(
    run_id: str,
    user_id: str,
    prompt: str,
    output: dict,
    status: str = "completed",
) -> None:
    """Persist the final result of a completed (or failed) task to Supabase.

    This used to be an LLM-invoked tool. It is now called directly by main.py
    after invoke_async() returns, using deterministic data (toolsUsed / downloadUrl
    captured via hooks) instead of trusting the model to self-report correctly.
    Calling it directly also means it always runs exactly once per request,
    instead of the model potentially retrying it dozens of times.

    Args:
        run_id: The run id for this request.
        user_id: The user id for this request.
        prompt: The original user prompt.
        output: The output dict to persist, e.g. {"reply": ..., "toolsUsed": [...]}
            or {"summary": ..., "downloadUrl": ...} or {"error": ...}.
        status: "completed" or "failed".
    """
    supabase = get_supabase()
    try:
        supabase.table("task_results").upsert({
            "run_id": run_id,
            "user_id": user_id,
            "prompt": prompt,
            "status": status,
            "output": output,
        }).execute()
    except Exception:
        error_detail = traceback.format_exc()
        # Best-effort: still try to record that persistence itself failed.
        try:
            supabase.table("task_results").upsert({
                "run_id": run_id,
                "user_id": user_id,
                "prompt": prompt,
                "status": "failed",
                "output": {"error": error_detail},
            }).execute()
        except Exception:
            # If even this fails (e.g. Supabase unreachable), don't crash the
            # request over a logging failure — the HTTP response still succeeds.
            pass