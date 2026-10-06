"""Cryptographic helpers: opaque tokens, password hashing, field encryption (docs/10 §2, §8)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import time

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.core.metrics import ARGON2_WAIT

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_token(nbytes: int = 32) -> str:
    """URL-safe random token (256 bits by default)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> bytes:
    """Tokens are stored only as SHA-256 digests: a DB leak yields no usable session."""
    return hashlib.sha256(token.encode()).digest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def crockford_base32(data: bytes) -> str:
    bits = int.from_bytes(data, "big")
    length = (len(data) * 8 + 4) // 5
    out = []
    for i in range(length):
        shift = (length - 1 - i) * 5
        out.append(CROCKFORD[(bits >> shift) & 0x1F])
    return "".join(out)


def human_code(n_chars: int = 10) -> str:
    """Short human-typable code (Crockford alphabet, no I/L/O/U ambiguity) for activation slips."""
    return "".join(secrets.choice(CROCKFORD) for _ in range(n_chars))


def normalise_human_code(code: str) -> str:
    cleaned = code.strip().upper().replace("-", "").replace(" ", "")
    return cleaned.replace("O", "0").replace("I", "1").replace("L", "1")


class PasswordService:
    """Argon2id with bounded concurrency per process (docs/11 §3).

    Hashing runs in a worker thread so the event loop is never blocked; a semaphore caps how many
    hashes run at once so a login burst cannot starve other requests of CPU/RAM.
    """

    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_kib,
            parallelism=settings.argon2_parallelism,
        )
        self._sem = asyncio.Semaphore(settings.argon2_max_concurrency)
        # A real hash of a random value: verifying against it costs the same as a real check, so
        # "unknown user" and "wrong password" take the same time (no account enumeration by timing).
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))

    async def _run[T](self, fn: object, *args: str) -> T:
        started = time.perf_counter()
        async with self._sem:
            ARGON2_WAIT.observe(time.perf_counter() - started)
            return await anyio.to_thread.run_sync(fn, *args)  # type: ignore[arg-type]

    async def hash(self, password: str) -> str:
        return await self._run(self._hasher.hash, password)

    async def verify(self, password_hash: str | None, password: str) -> bool:
        target = password_hash or self._dummy_hash
        try:
            ok: bool = await self._run(self._hasher.verify, target, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        return ok and password_hash is not None

    async def burn(self, password: str) -> None:
        """Spend the same work as a verification (for unknown accounts)."""
        await self.verify(None, password)

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


class FieldCipher:
    """AES-256-GCM for especially sensitive columns (TOTP secrets). Key derived from the app secret."""

    def __init__(self, secret: str) -> None:
        self._key = hashlib.sha256(b"scorecode-field-encryption:" + secret.encode()).digest()

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(12)
        ct = AESGCM(self._key).encrypt(nonce, plaintext.encode(), b"scorecode")
        return base64.urlsafe_b64encode(nonce + ct).decode()

    def decrypt(self, token: str) -> str:
        raw = base64.urlsafe_b64decode(token.encode())
        return AESGCM(self._key).decrypt(raw[:12], raw[12:], b"scorecode").decode()


def sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "123456789",
        "1234567890",
        "12345678910",
        "qwertyuiop",
        "iloveyou123",
        "admin12345",
        "welcome123",
        "letmein123",
        "abc1234567",
        "qwerty12345",
        "password@123",
        "india12345",
        "1q2w3e4r5t",
        "passw0rd123",
        "changeme123",
        "student123",
        "teacher123",
        "school1234",
        "college123",
    }
)


def password_problems(password: str, *, min_length: int, context: tuple[str, ...] = ()) -> list[str]:
    """NIST 800-63B style checks: length, not common, not derived from the user's identifiers."""
    problems = []
    if len(password) < min_length:
        problems.append(f"Use at least {min_length} characters.")
    if len(password) > 256:
        problems.append("Use at most 256 characters.")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        problems.append("This password is too common. Choose something less predictable.")
    for item in context:
        if item and len(item) >= 4 and item.lower() in lowered:
            problems.append("Don't include your email, enrollment number or institution name.")
            break
    return problems
