import os
import json
import logging

logger = logging.getLogger("StandaloneInjector.AIEngineConfig")

CONFIG_FILE_NAME = "ai_engine_config.json"

DEFAULT_CONFIG = {
    "provider": "ollama",  # "ollama" | "kimi" | "deepseek_cloud" | "openai"
    "director_provider": "ollama",
    "director_model": "llama3",
    "ollama": {
        "api_url": "http://localhost:11434/api/generate",
        "model_name": "llama3"
    },
    "kimi": {
        "api_url": "https://api.moonshot.cn/v1/chat/completions",
        "api_key": "",
        "model_name": "moonshot-v1-8k"
    },
    "deepseek_cloud": {
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key": "",
        "model_name": "deepseek-chat"
    },
    "openai": {
        "api_url": "https://api.openai.com/v1/chat/completions",
        "api_key": "",
        "model_name": "gpt-4o"
    }
}

def get_config_path() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, CONFIG_FILE_NAME)

def load_ai_config() -> dict:
    """ 載入 AI 引擎配置，若不存在則建立預設配置並嘗試自環境變數讀取 API Key """
    config_path = get_config_path()
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    for k, v in saved.items():
                        if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                            config[k].update(v)
                        else:
                            config[k] = v
        except Exception as e:
            logger.warning(f"讀取 AI 配置失敗 ({e})，使用預設配置")

    if not config["kimi"]["api_key"]:
        config["kimi"]["api_key"] = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY") or ""
    if not config["deepseek_cloud"]["api_key"]:
        config["deepseek_cloud"]["api_key"] = os.environ.get("DEEPSEEK_API_KEY") or ""
    if not config["openai"]["api_key"]:
        config["openai"]["api_key"] = os.environ.get("OPENAI_API_KEY") or ""

    return config

def save_ai_config(config: dict) -> bool:
    """ 儲存 AI 引擎配置到本機 JSON 檔案 """
    config_path = get_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"儲存 AI 配置失敗: {e}")
        return False
