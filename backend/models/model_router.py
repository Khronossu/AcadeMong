from config import MODEL_CONFIG

def get_model_config(intent: str) -> dict:
    for config in MODEL_CONFIG.values():
        if 'intents' in config and intent in config['intents']:
            return config
    return MODEL_CONFIG['primary']