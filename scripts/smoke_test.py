"""Run deployed-service smoke tests using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REQUIRED_LANGUAGES = {"ar", "en", "fr", "tr"}


def request_json(url: str, payload=None, api_key: str = ""):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-Key"] = api_key
    request = Request(url, data=data, headers=headers)
    with urlopen(request, timeout=180) as response:
        return response.status, json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="For example, https://tolba-translate.onrender.com")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        status, health = request_json(f"{base_url}/health")
        assert status == 200 and health == {"status": "ok"}, health

        status, languages = request_json(f"{base_url}/languages")
        available = {language["code"] for language in languages}
        assert status == 200 and REQUIRED_LANGUAGES <= available, available
        assert available <= REQUIRED_LANGUAGES, available

        checks = (
            ("en", "fr", "Find your dream match"),
            ("en", "tr", "Find your dream match"),
            ("ar", "fr", "مرحبا"),
        )
        for source, target, text in checks:
            status, result = request_json(
                f"{base_url}/translate",
                {"q": text, "source": source, "target": target, "format": "text"},
                args.api_key,
            )
            assert status == 200 and result.get("translatedText"), result
            print(f"PASS {source}->{target}: {result['translatedText']}")
    except (AssertionError, HTTPError, URLError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("PASS health and language checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
