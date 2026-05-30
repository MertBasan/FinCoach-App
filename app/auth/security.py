import bcrypt
from itsdangerous import URLSafeSerializer, BadSignature

from app.config import get_settings


_settings = get_settings()
_serializer = URLSafeSerializer(_settings.secret_key, salt="session")


# bcrypt has a 72-byte limit on inputs. We hash longer passwords through
# sha256 first to avoid silent truncation. This is the standard fix.
def _prepare(plain: str) -> bytes:
    raw = plain.encode("utf-8")
    if len(raw) <= 72:
        return raw
    import hashlib
    return hashlib.sha256(raw).hexdigest().encode("utf-8")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def make_session_token(user_id: str, firm_id: str) -> str:
    return _serializer.dumps({"uid": user_id, "fid": firm_id})


def read_session_token(token: str) -> dict | None:
    try:
        return _serializer.loads(token)
    except BadSignature:
        return None
