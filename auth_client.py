import os

import requests


FIREBASE_AUTH_TIMEOUT_SECONDS = 10
IDENTITY_TOOLKIT_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)
DEFAULT_FIREBASE_WEB_API_KEY = "AIzaSyDnna6qw_4IqwPvS6w1rXd9P7ZOMGoEPt8"


class AuthClientError(Exception):
    pass


class AuthConfigurationError(AuthClientError):
    pass


class InvalidCredentialsError(AuthClientError):
    pass


class DisabledUserError(AuthClientError):
    pass


class NetworkAuthError(AuthClientError):
    pass


def is_firebase_auth_configured() -> bool:
    return bool(
        os.getenv("FIREBASE_WEB_API_KEY", "").strip() or DEFAULT_FIREBASE_WEB_API_KEY
    )


def _firebase_web_api_key() -> str:
    api_key = os.getenv("FIREBASE_WEB_API_KEY", "").strip() or DEFAULT_FIREBASE_WEB_API_KEY
    if not api_key:
        raise AuthConfigurationError(
            "FIREBASE_WEB_API_KEY is not set. Online login requires a Firebase Web API key."
        )
    return api_key


def _map_firebase_error(error_code: str) -> AuthClientError:
    if error_code in {
        "INVALID_LOGIN_CREDENTIALS",
        "EMAIL_NOT_FOUND",
        "INVALID_PASSWORD",
        "MISSING_PASSWORD",
        "INVALID_EMAIL",
    }:
        return InvalidCredentialsError("Invalid email or password.")

    if error_code == "USER_DISABLED":
        return DisabledUserError("This user account has been disabled.")

    if error_code == "TOO_MANY_ATTEMPTS_TRY_LATER":
        return AuthClientError(
            "Too many failed login attempts. Please try again later."
        )

    return AuthClientError(f"Firebase Authentication failed: {error_code}")


def sign_in_email_password(email: str, password: str) -> dict:
    api_key = _firebase_web_api_key()
    endpoint = f"{IDENTITY_TOOLKIT_SIGN_IN_URL}?key={api_key}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=FIREBASE_AUTH_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise NetworkAuthError(
            "Network error while contacting Firebase Authentication."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise AuthClientError(
            "Firebase Authentication returned an unexpected response."
        ) from exc

    if not response.ok:
        error_code = data.get("error", {}).get("message", "UNKNOWN_ERROR")
        raise _map_firebase_error(error_code)

    return {
        "uid": data["localId"],
        "id_token": data["idToken"],
        "email": data.get("email", email).strip().lower(),
    }
