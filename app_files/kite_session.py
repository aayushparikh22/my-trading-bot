"""
Kite Session Manager - Provides always-valid KiteConnect sessions.

This module is the single source of truth for getting a valid Kite session.
It:
1. Checks if a cached access_token exists (in file or memory)
2. Validates it with a lightweight kite.profile() call
3. If invalid/expired, triggers auto-login to get a fresh token
4. Returns a ready-to-use KiteConnect instance + valid access_token

Usage:
    from app_files.kite_session import get_kite_session
    kite, access_token = get_kite_session()
"""

import os
import time
import logging
from kiteconnect import KiteConnect
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
TOKEN_PATH = os.path.join(PROJECT_DIR, "access_token.txt")
ENV_PATH = os.path.join(PROJECT_DIR, ".env")

# Load env
load_dotenv(ENV_PATH)

# In-memory cache
_kite = None
_access_token = None
_last_check = 0
CHECK_INTERVAL = 3600  # Re-validate token every 1 hour (seconds)


def _load_token_from_file():
    """Read saved access_token from access_token.txt"""
    try:
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "r") as f:
                token = f.read().strip()
                if token:
                    return token
    except Exception as e:
        logger.warning(f"[SESSION] Could not read token file: {e}")
    return None


def _save_token_to_file(token):
    """Persist access_token to file"""
    try:
        with open(TOKEN_PATH, "w") as f:
            f.write(token)
    except Exception as e:
        logger.warning(f"[SESSION] Could not save token file: {e}")


def _is_auto_login_enabled():
    """Check if auto-login is configured and enabled"""
    auto_login = os.getenv("KITE_AUTO_LOGIN", "false").strip().lower()
    if auto_login not in ("true", "1", "yes"):
        return False

    # Check that all required credentials exist
    required = ["KITE_API_KEY", "KITE_API_SECRET", "KITE_USER_ID", "KITE_PASSWORD", "KITE_TOTP_KEY"]
    for key in required:
        val = os.getenv(key, "").strip()
        if not val or val.startswith("YOUR_"):
            return False
    return True


def _do_auto_login():
    """Run the automated login and return (kite, access_token)"""
    from app_files.kite_login import login
    return login()


def get_kite_session(force_refresh=False):
    """
    Returns a validated (KiteConnect, access_token) tuple.

    Workflow:
    1. If we have a cached session and it's not stale, return it
    2. Try to load token from file → validate with profile() call
    3. Try to load token from .env → validate
    4. If all else fails and auto-login is enabled, do a fresh login
    5. If auto-login is not enabled, raise an error

    Args:
        force_refresh: If True, skip cache and re-validate/re-login

    Returns:
        tuple: (kite: KiteConnect, access_token: str)
    """
    global _kite, _access_token, _last_check

    now = time.time()
    api_key = os.getenv("KITE_API_KEY", "").strip()

    if not api_key:
        raise ValueError("KITE_API_KEY not set in .env")

    # Return cached session if still fresh
    if not force_refresh and _kite is not None and (now - _last_check) < CHECK_INTERVAL:
        return _kite, _access_token

    # === Attempt 1: Try token from file ===
    file_token = _load_token_from_file()
    if file_token:
        try:
            kite = KiteConnect(api_key=api_key)
            kite.set_access_token(file_token)
            kite.profile()  # Lightweight validation
            _kite = kite
            _access_token = file_token
            _last_check = now
            logger.info("[SESSION] ✅ Token from file is valid")
            return _kite, _access_token
        except Exception as e:
            logger.warning(f"[SESSION] Token from file invalid: {e}")

    # === Attempt 2: Try token from .env ===
    env_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
    if env_token and env_token != file_token:
        try:
            kite = KiteConnect(api_key=api_key)
            kite.set_access_token(env_token)
            kite.profile()
            _kite = kite
            _access_token = env_token
            _last_check = now
            _save_token_to_file(env_token)
            logger.info("[SESSION] ✅ Token from .env is valid")
            return _kite, _access_token
        except Exception as e:
            logger.warning(f"[SESSION] Token from .env invalid: {e}")

    # === Attempt 3: Auto-login ===
    if _is_auto_login_enabled():
        logger.info("[SESSION] 🔄 Tokens expired — running auto-login...")
        print("[SESSION] 🔄 Access token expired. Running auto-login...")
        try:
            kite, access_token = _do_auto_login()
            _kite = kite
            _access_token = access_token
            _last_check = now
            logger.info("[SESSION] ✅ Auto-login successful")
            return _kite, _access_token
        except Exception as e:
            logger.error(f"[SESSION] ❌ Auto-login failed: {e}")
            raise RuntimeError(
                f"Auto-login failed: {e}. "
                f"Check your KITE_PASSWORD and KITE_TOTP_KEY in .env"
            ) from e
    else:
        raise RuntimeError(
            "Kite access_token is expired and auto-login is not configured. "
            "Either: (1) Set KITE_AUTO_LOGIN=true with KITE_API_SECRET, KITE_PASSWORD, "
            "and KITE_TOTP_KEY in .env, or (2) Manually update KITE_ACCESS_TOKEN in .env."
        )


def get_access_token(force_refresh=False):
    """Convenience function — returns just the access_token string"""
    _, token = get_kite_session(force_refresh=force_refresh)
    return token


def invalidate_session():
    """Force the next call to re-validate / re-login"""
    global _kite, _access_token, _last_check
    _kite = None
    _access_token = None
    _last_check = 0
    logger.info("[SESSION] Session cache invalidated")


if __name__ == "__main__":
    """Test the session manager directly"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    try:
        kite, token = get_kite_session()
        profile = kite.profile()
        print(f"\n✅ Session valid!")
        print(f"   User: {profile.get('user_name', 'N/A')}")
        print(f"   Token: {token[:8]}...{token[-4:]}")
    except Exception as e:
        print(f"\n❌ Session test failed: {e}")
