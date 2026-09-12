import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from .agent import root_agent

load_dotenv()

app = FastAPI(title="Paralegal Sophia (Strands)")


class ChatRequest(BaseModel):
    prompt: str
    user_id: str
    run_id: str | None = None


@app.post("/chat")
async def chat(req: ChatRequest):
    run_id = req.run_id or str(uuid.uuid4())

    # invocation_state carries user_id/run_id to tools without polluting the
    # model's context — this is what tools read via tool_context.invocation_state
    result = await root_agent.invoke_async(
        req.prompt,
        user_id=req.user_id,
        run_id=run_id,
    )

    return {
        "run_id": run_id,
        "reply": str(result),
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# Local dev: uvicorn app_strands.main:app --reload --port 8080
# Lambda: wrap with mangum (pip install mangum) — see AWS Lambda deploy plan below
