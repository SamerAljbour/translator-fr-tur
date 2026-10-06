# Tolba Translation Service

A small, standalone LibreTranslate deployment for Tolba. It serves only Arabic (`ar`), English (`en`), French (`fr`), and Turkish (`tr`). It contains no Laravel or PHP code.

## API

- `GET /health` returns `{"status":"ok"}`.
- `GET /languages` lists the four installed languages and their targets.
- `POST /translate` accepts LibreTranslate JSON and returns `{"translatedText":"..."}`.

LibreTranslate 1.9.6 provides all three endpoints natively. This project adds only production configuration and optional shared-secret protection around `/translate`.

## Models and resource use

The build installs exactly six Argos models: `ar->en`, `en->ar`, `fr->en`, `en->fr`, `tr->en`, and `en->tr`. French, Turkish, and Arabic can therefore translate between one another through LibreTranslate's English pivot without downloading every available model. It also prepares the small MiniSBD sentence-boundary models for these four languages.

Models are downloaded during the Render build into `.argos-packages`, not on the first request. The build fails if a required model is unavailable or an unexpected model is installed. Model files are build artifacts and are intentionally excluded from Git.

LibreTranslate and its neural models are relatively heavy for Render's 512 MB Free instance. The service uses one worker and CPU inference to minimize memory. A free service spins down after 15 idle minutes, so its next request can take about a minute to wake, plus model-loading time. Free instances are intended for testing/hobby use and are not guaranteed for sustained translation traffic. Upgrade the instance if it runs out of memory or needs reliable latency.

## Local development

Python 3.13 is used on Render. Python 3.11-3.13 can be used locally.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
export ARGOS_PACKAGES_DIR=.argos-packages  # PowerShell: $env:ARGOS_PACKAGES_DIR='.argos-packages'
python scripts/setup_models.py
gunicorn --bind 127.0.0.1:5000 --workers 1 --threads 2 --timeout 180 'app:create_translation_app()'
```

Gunicorn does not run natively on Windows. On Windows, use WSL/Docker for the production command, or use LibreTranslate's Waitress server for a quick local check:

```powershell
$env:ARGOS_PACKAGES_DIR='.argos-packages'
libretranslate --host 127.0.0.1 --port 5000 --load-only en,ar,fr,tr --char-limit 5000 --batch-limit 1 --disable-web-ui --disable-files-translation
```

The direct `libretranslate` development command does not enable this project's optional shared-secret middleware.

## Deploy to Render

1. Push this repository to GitHub, GitLab, or Bitbucket.
2. In the Render Dashboard, select **New > Blueprint**.
3. Connect the repository and apply its `render.yaml`.
4. When prompted for `TRANSLATION_API_KEY`, leave it blank for the first deployment or enter a long random secret.
5. Wait for the build to download the six models and for `/health` to pass.

Render uses these commands from `render.yaml`:

```text
Build: bash scripts/build.sh
Start: gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 180 --access-logfile - --error-logfile - 'app:create_translation_app()'
```

`$PORT` is supplied by Render and is not hardcoded. After deployment, Render shows the public URL on the service page. With the configured service name it is normally:

```text
https://tolba-translate.onrender.com
```

Render may add a suffix if that subdomain is unavailable. Copy the exact URL shown in the dashboard.

## Environment variables

| Variable | Default/configured value | Purpose |
| --- | --- | --- |
| `PORT` | Supplied by Render | HTTP port used by Gunicorn |
| `ARGOS_PACKAGES_DIR` | `.argos-packages` | Build/runtime model location |
| `XDG_DATA_HOME` | `.argos-data` | Argos package-index data inside the build artifact |
| `XDG_CACHE_HOME` | `.argos-cache` | Argos cache inside the build artifact |
| `XDG_CONFIG_HOME` | `.argos-config` | Argos configuration inside the build artifact |
| `ARGOS_DEVICE_TYPE` | `cpu` | Avoids GPU initialization |
| `ARGOS_CHUNK_TYPE` | `MINISBD` | Uses the lightweight sentence boundary detector |
| `TRANSLATION_CHAR_LIMIT` | `5000` | Maximum characters per translation request |
| `TRANSLATION_API_KEY` | Empty | If set, protects `POST /translate` |
| `LOG_LEVEL` | `INFO` | Application log level |

Do not set LibreTranslate's `LT_UPDATE_MODELS` at runtime. The required models are prepared at build time.

### Optional API secret

If `TRANSLATION_API_KEY` is non-empty, `/translate` requires the same value in one of these forms:

- JSON/form field `api_key` (compatible with normal LibreTranslate clients)
- `X-API-Key: <secret>`
- `Authorization: Bearer <secret>`

`/health` and `/languages` stay public so Render and Tolba can verify readiness. Secrets are compared in constant time and are never logged. Rotate the value in Render and Tolba together.

LibreTranslate 1.9.6 adds permissive CORS headers by default. This app removes them because Tolba calls the API server-to-server. The web UI, file translation, debug mode, and metrics are disabled. LibreTranslate provides clean JSON errors for invalid input (`400`), rate limits (`429`, if configured later), and translation failures (`500`). Gunicorn emits access/errors without logging request bodies.

## Test the deployed service

Replace the base URL with the one shown by Render. If protection is enabled, add `"api_key":"YOUR_SECRET"` to translation JSON or send `-H "X-API-Key: YOUR_SECRET"`.

Health:

```bash
curl https://YOUR-SERVICE.onrender.com/health
```

Languages:

```bash
curl https://YOUR-SERVICE.onrender.com/languages
```

English to French:

```bash
curl -X POST https://YOUR-SERVICE.onrender.com/translate \
  -H "Content-Type: application/json" \
  -d '{"q":"Find your dream match","source":"en","target":"fr","format":"text"}'
```

English to Turkish:

```bash
curl -X POST https://YOUR-SERVICE.onrender.com/translate \
  -H "Content-Type: application/json" \
  -d '{"q":"Find your dream match","source":"en","target":"tr","format":"text"}'
```

Arabic to French:

```bash
curl -X POST https://YOUR-SERVICE.onrender.com/translate \
  -H "Content-Type: application/json" \
  -d '{"q":"مرحبا","source":"ar","target":"fr","format":"text"}'
```

Run all smoke tests (health, exact language set, EN->FR, EN->TR, and AR->FR):

```bash
python scripts/smoke_test.py https://YOUR-SERVICE.onrender.com
python scripts/smoke_test.py https://YOUR-SERVICE.onrender.com --api-key YOUR_SECRET
```

## Connect Tolba

Copy these values into Tolba's `.env`, using the exact Render URL and the same secret configured on Render:

```dotenv
TRANSLATION_PROVIDER=libretranslate
TRANSLATION_API_URL=https://YOUR-SERVICE.onrender.com
TRANSLATION_API_KEY=
TRANSLATION_TIMEOUT=120
```

For a protected deployment:

```dotenv
TRANSLATION_PROVIDER=libretranslate
TRANSLATION_API_URL=https://YOUR-SERVICE.onrender.com
TRANSLATION_API_KEY=YOUR_LONG_RANDOM_SECRET
TRANSLATION_TIMEOUT=120
```

Tolba should post JSON to `${TRANSLATION_API_URL}/translate`. Render terminates TLS, so Tolba communicates with the public service over HTTPS.

## Operational notes

- Startup and model setup are logged, as are failed translation statuses. Text and secrets are not logged.
- The service limits a request to 5,000 translation characters and a batch to one item. Change `TRANSLATION_CHAR_LIMIT` in Render if needed.
- LibreTranslate supports request-rate limits through `LT_REQ_LIMIT`; it is unset initially. Set it later if the public endpoint needs basic per-client throttling.
- Render's filesystem is ephemeral at runtime. Models survive because they are included in each build artifact; every new build prepares them again.
- MiniSBD models are stored in the build artifact's `.minisbd` directory, so translations never need a runtime download.
