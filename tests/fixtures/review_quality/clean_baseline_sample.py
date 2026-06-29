def normalize_name(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def build_label(prefix: str, name: str) -> str:
    normalized = normalize_name(name)
    return f"{prefix}:{normalized}"
