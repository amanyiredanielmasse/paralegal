import uuid
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from .agent import root_agent
from .lib.request_context import current_user_id, current_run_id, current_tracking, ToolTracking
from .tools.supabase_writer import write_result

load_dotenv()

app = FastAPI(title="Paralegal Sophia (Strands)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_SUB_AGENT_NAMES = {"research_agent", "case_agent", "drafting_agent"}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    mode: Literal["chat", "agent"] = "chat"
    user_id: str
    run_id: str | None = None


@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.messages:
        return {"error": "messages must not be empty"}

    run_id = req.run_id or str(uuid.uuid4())
    last_prompt = req.messages[-1].content

    # Forward full conversation history so the orchestrator has multi-turn
    # context, not just the latest message.
    strands_messages = [
        {"role": m.role, "content": [{"text": m.content}]}
        for m in req.messages
    ]

    # mode is an explicit hint from the UI toggle (user deciding "I want a
    # court doc" vs "I'm just researching") layered on top of the
    # orchestrator's own judgement from ORCHESTRATOR_PROMPT.
    if req.mode == "agent":
        strands_messages.append({
            "role": "user",
            "content": [{
                "text": (
                    "(The user has explicitly selected document-drafting mode: "
                    "they want a formal court submission drafted and saved as a "
                    "Word document, not just research or a conversational answer.)"
                )
            }],
        })

    tracking = ToolTracking()
    token_user = current_user_id.set(req.user_id)
    token_run = current_run_id.set(run_id)
    token_tracking = current_tracking.set(tracking)

    try:
        result = await root_agent.invoke_async(strands_messages)
    except Exception as e:
        write_result(
            run_id=run_id,
            user_id=req.user_id,
            prompt=last_prompt,
            output={"error": str(e)},
            status="failed",
        )
        return {"run_id": run_id, "error": str(e)}
    finally:
        current_user_id.reset(token_user)
        current_run_id.reset(token_run)
        current_tracking.reset(token_tracking)

    reply_text = str(result)
    tools_used = sorted(tracking.tools_used - _SUB_AGENT_NAMES)
    download_url = tracking.download_url

    if req.mode == "agent" and download_url:
        output = {"summary": reply_text, "downloadUrl": download_url}
    else:
        output = {"reply": reply_text, "toolsUsed": tools_used}

    write_result(
        run_id=run_id,
        user_id=req.user_id,
        prompt=last_prompt,
        output=output,
        status="completed",
    )

    return {"run_id": run_id, **output}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# Local dev: uvicorn app.main:app --reload --port 8080
# Lambda: wrap with mangum (pip install mangum) — see AWS Lambda deploy plan below