from fastapi import APIRouter
from models.model_router import get_model_config
from models.ollama_client import chat

router = APIRouter()


@router.get("/test")
async def test_model(intent: str = "general"):
    config = get_model_config(intent)
    response = await chat(
        model=config["model"],
        messages=[{"role": "user", "content": "Say hello in Thai."}],
        temperature=config["temperature"],
        top_p=config["top_p"],
        max_tokens=config["max_tokens"],
    )
    return {
        "intent": intent,
        "model": config["model"],
        "response": response,
    }
