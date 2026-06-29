import pickle


def load_cached_payload(payload: bytes):
    return pickle.loads(payload)
