import requests


def post_event(endpoint: str, payload: dict):
    return requests.post(endpoint, json=payload, timeout=5)
