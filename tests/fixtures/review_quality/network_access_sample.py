import requests


def fetch_status():
    return requests.get("https://example.com/status", timeout=5)
