"""
Automated Kite Connect Login
Handles the full multi-step Zerodha login (credentials + TOTP 2FA)
and generates a fresh access_token without manual browser intervention.

Based on: https://medium.com/@yasheshlele/how-to-fully-automate-your-zerodha-kite-api-login-with-python-1bf6001f34fe
"""

import os
import json
import time
import logging
import pyotp
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from kiteconnect import KiteConnect
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
TOKEN_PATH = os.path.join(PROJECT_DIR, "access_token.txt")
ENV_PATH = os.path.join(PROJECT_DIR, ".env")

# Load .env from project root
load_dotenv(ENV_PATH)


def _get_credentials():
    """Load credentials from environment variables"""
    api_key = os.getenv("KITE_API_KEY", "").strip()
    api_secret = os.getenv("KITE_API_SECRET", "").strip()
    user_id = os.getenv("KITE_USER_ID", "").strip()
    password = os.getenv("KITE_PASSWORD", "").strip()
    totp_key = os.getenv("KITE_TOTP_KEY", "").strip()

    missing = []
    if not api_key:
        missing.append("KITE_API_KEY")
    if not api_secret:
        missing.append("KITE_API_SECRET")
    if not user_id:
        missing.append("KITE_USER_ID")
    if not password:
        missing.append("KITE_PASSWORD")
    if not totp_key:
        missing.append("KITE_TOTP_KEY")

    if missing:
        raise ValueError(
            f"Missing credentials in .env: {', '.join(missing)}. "
            f"Please fill them in {ENV_PATH}"
        )

    return api_key, api_secret, user_id, password, totp_key


def login():
    """
    Perform automated Kite login:
    1. Open Kite login page (obtain session cookies)
    2. POST login credentials (user_id + password)
    3. POST TOTP 2FA code
    4. Extract request_token from redirect URL
    5. Exchange request_token for access_token via Kite SDK
    6. Save access_token to file and return KiteConnect instance

    Returns:
        tuple: (kite: KiteConnect, access_token: str)

    Raises:
        Exception: If any step of the login fails
    """
    api_key, api_secret, user_id, password, totp_key = _get_credentials()

    logger.info("[AUTO-LOGIN] Starting automated Kite login...")

    session = requests.Session()

    try:
        # Step 1: Hit the Kite login page to establish a session
        login_url = f"https://kite.trade/connect/login?v=3&api_key={api_key}"
        login_page_res = session.get(url=login_url)
        login_page_url = login_page_res.url  # Captures the full redirect URL
        logger.info("[AUTO-LOGIN] Step 1/5: Login page loaded")

        # Step 2: POST login credentials
        login_resp = session.post(
            url="https://kite.zerodha.com/api/login",
            data={"user_id": user_id, "password": password}
        )
        login_json = login_resp.json()

        if "data" not in login_json or "request_id" not in login_json.get("data", {}):
            raise Exception(f"Login failed (credentials). Response: {login_json}")

        request_id = login_json["data"]["request_id"]
        logger.info("[AUTO-LOGIN] Step 2/5: Credentials accepted")

        # Step 3: POST TOTP 2FA
        totp_code = pyotp.TOTP(totp_key).now()
        twofa_resp = session.post(
            url="https://kite.zerodha.com/api/twofa",
            data={
                "user_id": user_id,
                "request_id": request_id,
                "twofa_value": totp_code,
            }
        )
        twofa_json = twofa_resp.json()

        if twofa_json.get("status") != "success":
            raise Exception(f"2FA failed: {twofa_json.get('message', twofa_json)}")

        logger.info("[AUTO-LOGIN] Step 3/5: TOTP 2FA verified")

        # Step 4: Follow redirect to get request_token
        # IMPORTANT: Use allow_redirects=False to capture the redirect URL
        # without actually connecting to 127.0.0.1 (which has no server)
        final_response = session.get(url=login_page_url, allow_redirects=False)

        # The request_token may be in the redirect Location header (302)
        # or in the final URL if redirects were followed partially
        redirect_url = final_response.headers.get("Location", final_response.url)

        if "request_token" not in redirect_url:
            # Try following redirects but catch connection errors to localhost
            try:
                final_response = session.get(url=login_page_url, allow_redirects=True)
                redirect_url = final_response.url
            except requests.exceptions.ConnectionError as ce:
                # The redirect to 127.0.0.1 failed (expected — no server there)
                # Extract the URL from the exception or response history
                if final_response.history:
                    redirect_url = final_response.history[-1].headers.get("Location", "")
                elif hasattr(ce, 'request') and ce.request:
                    redirect_url = ce.request.url
                else:
                    raise Exception(f"Could not extract request_token from redirect: {ce}")

        if "request_token" not in redirect_url:
            raise Exception(
                f"Failed to get request_token from redirect. "
                f"Final URL: {redirect_url}"
            )

        request_token = parse_qs(urlparse(redirect_url).query)["request_token"][0]
        logger.info("[AUTO-LOGIN] Step 4/5: request_token obtained")

        # Step 5: Exchange request_token for access_token
        kite = KiteConnect(api_key=api_key)
        session_data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = session_data["access_token"]

        # Save to file for persistence
        with open(TOKEN_PATH, "w") as f:
            f.write(access_token)

        kite.set_access_token(access_token)
        logger.info(f"[AUTO-LOGIN] Step 5/5: access_token acquired and saved to {TOKEN_PATH}")
        print(f"[AUTO-LOGIN] ✅ Zerodha session ready at {datetime.now().strftime('%H:%M:%S')}")

        return kite, access_token

    except Exception as e:
        logger.error(f"[AUTO-LOGIN] ❌ Login failed: {e}")
        print(f"[AUTO-LOGIN] ❌ Login failed: {e}")
        raise


def get_fresh_access_token():
    """
    Convenience function that returns just the access_token string.
    Used by the trading service to refresh credentials.
    """
    _, access_token = login()
    return access_token


if __name__ == "__main__":
    """Test the login by running: python kite_login.py"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    try:
        kite, token = login()
        profile = kite.profile()
        print(f"\n✅ Login successful!")
        print(f"   User: {profile.get('user_name', 'N/A')}")
        print(f"   Email: {profile.get('email', 'N/A')}")
        print(f"   Token: {token[:8]}...{token[-4:]}")
    except Exception as e:
        print(f"\n❌ Login test failed: {e}")
        print("\nCheck your .env file has these filled in:")
        print("  KITE_API_KEY, KITE_API_SECRET, KITE_USER_ID, KITE_PASSWORD, KITE_TOTP_KEY")
