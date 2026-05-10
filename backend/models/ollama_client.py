import httpx
import os

OLLAMA_BASE_URL = f"http://{os.getenv('OLLAMA_HOST', 'ollama')}:{os.getenv('OLLAMA_PORT', 11434)}"

async def chat(model, messages, temperature, top_p, max_tokens):
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f'{OLLAMA_BASE_URL}/api/chat',
            json={
                "model": model,
                "messages": messages,
                "options": {
                    "temperature": temperature,
                    "top_p": top_p,
                    "num_predict": max_tokens
                    },
                "stream": False
            }
        )
        response.raise_for_status()
        return response.json()['message']['content']



async def embed(model, text):
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f'{OLLAMA_BASE_URL}/api/embed',
            json={
                "model": model,
                "input": text
            }
        )
        response.raise_for_status()
        return response.json()['embeddings'][0]

