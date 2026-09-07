import hmac
import hashlib
import struct
import time
import secrets
import urllib.parse


def generate_secret(length: int = 32) -> str:
    random_bytes = secrets.token_bytes(length)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    result = []
    bits = 0
    value = 0
    for byte in random_bytes:
        value = (value << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            result.append(alphabet[(value >> bits) & 31])
    if bits > 0:
        result.append(alphabet[(value << (5 - bits)) & 31])
    return "".join(result[:length])


def _decode_secret(secret: str) -> bytes:
    secret = secret.upper().rstrip("=")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = 0
    value = 0
    result = bytearray()
    for char in secret:
        if char not in alphabet:
            continue
        value = (value << 5) | alphabet.index(char)
        bits += 5
        if bits >= 8:
            bits -= 8
            result.append((value >> bits) & 0xFF)
    return bytes(result)


def hotp(secret: str, counter: int, digits: int = 6) -> str:
    key = _decode_secret(secret)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    binary = ((h[offset] & 0x7F) << 24) | ((h[offset + 1] & 0xFF) << 16) | \
             ((h[offset + 2] & 0xFF) << 8) | (h[offset + 3] & 0xFF)
    otp = binary % (10 ** digits)
    return str(otp).zfill(digits)


def totp(secret: str, digits: int = 6, period: int = 30, for_time: int = None) -> str:
    if for_time is None:
        for_time = int(time.time())
    counter = for_time // period
    return hotp(secret, counter, digits)


def verify_totp(secret: str, token: str, digits: int = 6, period: int = 30,
                valid_window: int = 1) -> bool:
    token = (token or "").strip()
    if len(token) != digits or not token.isdigit():
        return False
    now = int(time.time())
    for i in range(-valid_window, valid_window + 1):
        expected = totp(secret, digits, period, now + i * period)
        if hmac.compare_digest(expected, token):
            return True
    return False


def get_provisioning_uri(secret: str, name: str, issuer: str = "DarkSword") -> str:
    params = {
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": 6,
        "period": 30,
    }
    label = urllib.parse.quote(f"{issuer}:{name}")
    query = urllib.parse.urlencode(params)
    return f"otpauth://totp/{label}?{query}"
