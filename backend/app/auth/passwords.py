"""Password hashing with Argon2 (the current recommendation). Passwords themselves are never stored."""

from pwdlib import PasswordHash

MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHash.recommended()  # Argon2id
# Checked when the username doesn't exist, so a failed login takes the same time either way
# and response times can't reveal which usernames exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def spend_equal_time(password: str) -> None:
    _hasher.verify(password, _DUMMY_HASH)
