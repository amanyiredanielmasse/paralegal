from strands import tool, ToolContext
from ..lib.supabase_client import get_supabase
from ..lib.request_context import current_user_id


def _apply_filters(db_query, *, client_name=None, file_no=None,
                    court_case_no=None, nature_of_case=None, status=None):
    """Apply whichever structured filters are present, AND'd together."""
    if client_name:
        db_query = db_query.ilike("client_name", f"%{client_name.strip()}%")
    if file_no:
        db_query = db_query.ilike("lac_file_no", f"%{file_no.strip()}%")
    if court_case_no:
        db_query = db_query.ilike("court_case_no", f"%{court_case_no.strip()}%")
    if nature_of_case:
        db_query = db_query.ilike("nature_of_case", f"%{nature_of_case.strip()}%")
    if status:
        db_query = db_query.ilike("status", f"%{status.strip()}%")
    return db_query


def _format_rows(rows: list[dict]) -> str:
    out = []
    for c in rows:
        lines = [
            f"Case: {c.get('client_name')} | File: {c.get('lac_file_no')} | Court: {c.get('court_case_no') or 'N/A'}",
            f"Date: {c.get('date')} | Nature: {c.get('nature_of_case') or 'N/A'} | Status: {c.get('status') or 'N/A'}",
            f"Action taken: {c.get('action_taken') or 'N/A'}",
        ]
        if c.get("notes"):
            lines.append(f"Notes: {c['notes']}")
        out.append("\n".join(lines))
    return "\n\n".join(out)


@tool(context=True)
def read_cases_db(
    client_name: str | None = None,
    file_no: str | None = None,
    court_case_no: str | None = None,
    nature_of_case: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    *,
    tool_context: ToolContext,
) -> str:
    """Read case records from the user's case database.
    Use when the user asks about their specific cases, clients, or file numbers.

    Fill in whichever fields you can confidently infer from the user's message
    and leave the rest as None. Do not guess — only set a field if the user's
    message clearly implies it (e.g. "the Nakato case" -> client_name="Nakato";
    "file LAC/2024/019" -> file_no="LAC/2024/019"; "that robbery case" ->
    nature_of_case="robbery").

    If the user's message is a loose or ambiguous description that doesn't cleanly
    map to one field (e.g. "that land case from last month", "the one about the
    boundary dispute"), put the relevant terms in `keyword` instead. `keyword` is
    matched broadly across client name, file number, court case number, nature of
    case, and notes.

    You can combine `keyword` with structured fields, e.g. client_name="Okello"
    plus keyword="boundary" to narrow within a client's cases.

    If no fields are known at all, call the tool with everything None — it will
    return the user's most recent cases as a starting point.
    """
    # NOTE: not tool_context.invocation_state.get("user_id") — Strands' agent-as-tool
    # wrapper doesn't forward invocation_state to sub-agents, so that would be None
    # whenever this runs inside case_agent (which is the whole point of this tool).
    user_id: str | None = current_user_id.get()
    supabase = get_supabase()

    structured = dict(
        client_name=client_name, file_no=file_no, court_case_no=court_case_no,
        nature_of_case=nature_of_case, status=status,
    )
    has_structured = any(structured.values())

    # --- Tier 1: structured filters (+ optional keyword) as given ---
    db_query = (
        supabase.table("cases")
        .select("*")
        .eq("user_id", user_id)
        .order("date", desc=True)
        .limit(20)
    )
    db_query = _apply_filters(db_query, **structured)
    if keyword:
        kw = keyword.strip()
        db_query = db_query.or_(
            f"client_name.ilike.%{kw}%,lac_file_no.ilike.%{kw}%,"
            f"court_case_no.ilike.%{kw}%,nature_of_case.ilike.%{kw}%,notes.ilike.%{kw}%"
        )

    result = db_query.execute()
    print(f"[read_cases_db] tier=1 user_id={user_id!r} filters={structured} "
          f"keyword={keyword!r} rows={len(result.data)}")

    if result.data:
        return _format_rows(result.data)

    # --- Tier 2: relax and retry, keeping only the strongest identifiers ---
    # file_no / court_case_no are near-unique; client_name / keyword are decent;
    # nature_of_case / status are the weakest signals, so drop those first.
    if has_structured or keyword:
        strong_query = (
            supabase.table("cases")
            .select("*")
            .eq("user_id", user_id)
            .order("date", desc=True)
            .limit(20)
        )
        strong_query = _apply_filters(
            strong_query,
            client_name=client_name,
            file_no=file_no,
            court_case_no=court_case_no,
        )
        if keyword and not (client_name or file_no or court_case_no):
            kw = keyword.strip()
            strong_query = strong_query.or_(
                f"client_name.ilike.%{kw}%,lac_file_no.ilike.%{kw}%,court_case_no.ilike.%{kw}%"
            )

        result = strong_query.execute()
        print(f"[read_cases_db] tier=2 user_id={user_id!r} rows={len(result.data)}")

        if result.data:
            return (
                "No exact match for the given filters, but here are close matches "
                "based on client name / file number / court case number:\n\n"
                + _format_rows(result.data)
            )

    # --- Tier 3: nothing matched at all — surface known client names so the
    # model can ask the user to pick one, rather than dead-ending ---
    names_result = (
        supabase.table("cases")
        .select("client_name")
        .eq("user_id", user_id)
        .order("date", desc=True)
        .limit(100)
        .execute()
    )
    seen = []
    for row in names_result.data:
        n = row.get("client_name")
        if n and n not in seen:
            seen.append(n)
    print(f"[read_cases_db] tier=3 user_id={user_id!r} distinct_names={len(seen)}")

    if not seen:
        return "No cases found in the database for this user."

    names_list = "\n".join(f"- {n}" for n in seen[:30])
    return (
        "No matching case found for the given details. "
        "Ask the user to confirm a client name or file/case number. "
        f"Here are the client names currently on file to choose from:\n\n{names_list}"
    )
