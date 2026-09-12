import os
import httpx

OPENROUTER_EMBEDDING_MODEL = os.environ.get("OPENROUTER_EMBEDDING_MODEL", "baai/bge-m3")
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"


def embed_text(text: str) -> list[float]:
    """Embed text using OpenRouter (default model: baai/bge-m3, 1024-dim)."""
    api_key = os.environ["OPENROUTER_API_KEY"]

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            OPENROUTER_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_EMBEDDING_MODEL,
                "input": text,
            },
        )

    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter embeddings error {resp.status_code}: {resp.text}")

    data = resp.json()
    # OpenAI-compatible response shape: {"data": [{"embedding": [...]}], ...}
    return data["data"][0]["embedding"]
