"""Құпиясөздер, тіркелу және кіру."""
import hashlib
import hmac
import os
import re
import secrets
import string

import db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def generate_password(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    alphabet = "".join(c for c in alphabet if c not in "l1IO0o")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_code(length: int = 6) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def get_user_by_email(email):
    return db.query_one("SELECT * FROM users WHERE lower(email)=lower(?)", (email.strip(),))


def get_user(uid):
    return db.query_one("SELECT * FROM users WHERE id=?", (uid,))


def create_user(email, name, password, role):
    return db.insert(
        "INSERT INTO users (email, name, password_hash, role, created_at) VALUES (?,?,?,?,?)",
        (email.strip().lower(), name.strip(), hash_password(password), role, db.now()),
    )


def login(email, password):
    user = get_user_by_email(email)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def set_password(uid, password):
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), uid))
