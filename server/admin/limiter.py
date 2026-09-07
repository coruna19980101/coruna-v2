try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
    LIMITER_AVAILABLE = True
except ImportError:
    limiter = None
    LIMITER_AVAILABLE = False


def rate_limit(rate: str):
    def decorator(func):
        if LIMITER_AVAILABLE and limiter is not None:
            return limiter.limit(rate)(func)
        return func
    return decorator
