import hashlib
import hmac
import secrets


ITERATIONS = 260_000


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt),
            int(iterations),
        )
        return hmac.compare_digest(actual.hex(), expected)
    except (TypeError, ValueError):
        return False
