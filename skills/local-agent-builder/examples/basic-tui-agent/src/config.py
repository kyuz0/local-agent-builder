import os
import sys
import yaml
import copy

def _get_config_path_from_args():
    for i, arg in enumerate(sys.argv):
        if arg in ["--config", "-c"] and i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i+1])
    return None

_AGENT_NAME = "basic-tui-agent"
_DEFAULT_CONFIG_DIR = os.path.expanduser(f"~/.{_AGENT_NAME}")
_CONFIG_PATH = _get_config_path_from_args() or os.path.join(_DEFAULT_CONFIG_DIR, "config.yaml")

_DEFAULTS = {
    "api": {
        "openai_base_url": "http://localhost:8080/v1",
        "openai_model": "local-model",
    },
    "settings": {
        "enable_thinking": False,
        "quotas": {},
        "workspace": {
            "type": "memory",
            "dir": "."
        }
    }
}

cfg: dict = {}

def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge overlay into base, recursively for nested dicts."""
    result = copy.deepcopy(base)
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def load_config() -> dict:
    """Load config from YAML file, falling back to defaults for missing keys."""
    global cfg
    file_cfg = {}
    
    if not os.path.exists(_CONFIG_PATH):
        bundled_config = os.path.join(os.path.dirname(__file__), "config_template.yaml")
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        if os.path.exists(bundled_config):
            import shutil
            shutil.copy(bundled_config, _CONFIG_PATH)
        else:
            with open(_CONFIG_PATH, "w") as f:
                yaml.dump(_DEFAULTS, f, default_flow_style=False, sort_keys=False)

    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r") as f:
            file_cfg = yaml.safe_load(f) or {}
            
    cfg = _deep_merge(_DEFAULTS, file_cfg)

    # Overlay API keys from environment if set (env takes priority for secrets)
    if os.environ.get("OPENAI_API_BASE"):
        cfg["api"]["openai_base_url"] = os.environ["OPENAI_API_BASE"]
    if os.environ.get("OPENAI_MODEL"):
        cfg["api"]["openai_model"] = os.environ["OPENAI_MODEL"]

    return cfg

def save_config() -> None:
    """Persist the current config dict back to config.yaml."""
    save_data = copy.deepcopy(cfg)
    
    # Strip out sensitive API keys before writing if any are stored in keys
    if "api" in save_data:
        save_data["api"].pop("openai_api_key", None)
        
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(save_data, f, default_flow_style=False, sort_keys=False)

# Auto-initialize on import so it's globally available
load_config()
