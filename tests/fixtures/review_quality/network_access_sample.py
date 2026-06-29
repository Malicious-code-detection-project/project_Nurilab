import requests


def fetch_status(url: str):
    return requests.get(url, timeout=5)
