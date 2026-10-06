"""Production entry point for the Tolba LibreTranslate service."""

from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("ARGOS_PACKAGES_DIR", str(_PROJECT_ROOT / ".argos-packages"))
os.environ.setdefault("XDG_DATA_HOME", str(_PROJECT_ROOT / ".argos-data"))
os.environ.setdefault("XDG_CACHE_HOME", str(_PROJECT_ROOT / ".argos-cache"))
os.environ.setdefault("XDG_CONFIG_HOME", str(_PROJECT_ROOT / ".argos-config"))

from flask import jsonify, request
from libretranslate.app import create_app
from libretranslate.main import get_parser
from minisbd import models as minisbd_models

minisbd_models.cache_dir = str(_PROJECT_ROOT / ".minisbd")


SUPPORTED_LANGUAGES = ("en", "ar", "fr", "tr")
DEFAULT_CHAR_LIMIT = 5_000

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("tolba-translate")
logging.getLogger("argostranslate").setLevel(logging.WARNING)
logging.getLogger("argostranslate.utils").setLevel(logging.WARNING)
logging.getLogger("libretranslate").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def _request_api_key() -> str:
    header_key = request.headers.get("X-API-Key", "")
    if header_key:
        return header_key

    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator and scheme.lower() == "bearer":
        return token

    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            key = payload.get("api_key", "")
            return key if isinstance(key, str) else ""

    return request.form.get("api_key", "")


def create_translation_app():
    """Create LibreTranslate with Tolba's production-safe configuration."""
    char_limit = _positive_int_from_env(
        "TRANSLATION_CHAR_LIMIT", DEFAULT_CHAR_LIMIT
    )
    args = get_parser().parse_args(
        [
            "--load-only",
            ",".join(SUPPORTED_LANGUAGES),
            "--char-limit",
            str(char_limit),
            "--batch-limit",
            "1",
            "--disable-web-ui",
            "--disable-files-translation",
        ]
    )

    logger.info(
        "Starting LibreTranslate with languages=%s char_limit=%d",
        ",".join(SUPPORTED_LANGUAGES),
        char_limit,
    )
    app = create_app(args)
    app.config.update(
        DEBUG=False,
        MAX_CONTENT_LENGTH=max(65_536, char_limit * 8),
        PROPAGATE_EXCEPTIONS=False,
    )

    api_key = os.getenv("TRANSLATION_API_KEY", "")
    if api_key:
        logger.info("Optional API-key protection is enabled for /translate")
    else:
        logger.warning("TRANSLATION_API_KEY is empty; /translate is public")

    @app.before_request
    def require_translation_api_key():
        if request.path != "/translate" or not api_key:
            return None

        supplied_key = _request_api_key()
        if not hmac.compare_digest(supplied_key, api_key):
            return jsonify({"error": "Invalid or missing API key"}), 401
        return None

    @app.after_request
    def apply_production_headers(response):
        # LibreTranslate currently adds permissive CORS headers. Tolba calls this
        # service server-to-server, so remove them instead of exposing browser use.
        for header in (
            "Access-Control-Allow-Origin",
            "Access-Control-Allow-Headers",
            "Access-Control-Expose-Headers",
            "Access-Control-Allow-Methods",
            "Access-Control-Allow-Credentials",
            "Access-Control-Max-Age",
        ):
            response.headers.pop(header, None)

        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.path == "/translate" and response.status_code >= 400:
            logger.warning("Translation request failed status=%d", response.status_code)
        return response

    return app
