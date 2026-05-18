from pathlib import Path


def read_config(path: str) -> str:
    config_path = Path(path)
    return config_path.read_text(encoding="utf-8")
