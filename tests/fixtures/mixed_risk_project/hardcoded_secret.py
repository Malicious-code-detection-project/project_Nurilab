# Test fixture only. This is not a real credential.
API_KEY = "demo_api_key_value_not_real"


def masked_key() -> str:
    return API_KEY[:4]
