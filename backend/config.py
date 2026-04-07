MODEL_CONFIG = {
    "primary": {
        "model": "llama3.2:1b",  # TODO: switch to scb10x/llama3.1-typhoon2-8b-instruct when pulled
        "intents": ["general", "eligibility", "recommendation", "career"],
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 1000
    },
    "rag": {
        "model": "llama3.2:1b",  # TODO: switch to scb10x/llama3.1-typhoon2-8b-instruct when pulled
        "intents": ["preparation", "comparison"],
        "temperature": 0.2,   # lower — needs to stay grounded to retrieved context
        "top_p": 0.85,
        "max_tokens": 1500
    },
    "embedding": {
        "model": "nomic-embed-text"
    },
    "fallback": {
        "model": "llama3.1-8b",
        "trigger": "primary_model_failure"
    }
}