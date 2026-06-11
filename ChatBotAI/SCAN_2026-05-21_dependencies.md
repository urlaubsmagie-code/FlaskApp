# Dependency Freshness & Vulnerability Scan — 2026-05-21

Project: `C:\Users\admin\Documents\FlaskApp\ChatBotAI`
Source: `requirements.txt` (all pins use `>=`, so installed versions may differ — this scan compares the floor pin to current PyPI latest).
Scan method: PyPI JSON metadata (`https://pypi.org/pypi/<pkg>/json`) fetched 2026-05-21.

## Dependency status table

| Package | Pinned (floor) | Latest stable (2026-05) | Behind by | Known CVEs / notable changes |
|---|---|---|---|---|
| flask | >=3.0.0 | 3.1.3 (2026-02-19) | 1 minor | Flask 3.1 dropped Python 3.8; added `Flask.async_to_sync`, `Config.from_dotenv()` helper, `app.url_map.lifespan` improvements. No active CVEs against 3.x. Recommend bump floor to `>=3.1.0`. |
| flask-sqlalchemy | >=3.1.1 | 3.1.1 (2023-09-11) | Current | Latest. Note: 3.1.x is the SQLAlchemy 2.0 compatible line. No CVEs. |
| flask-migrate | >=4.0.0 | 4.1.0 (2025-01-10) | 1 minor | Adds support for Alembic 1.13+ features (post-write hooks, multidb). No CVEs. |
| flask-login | >=0.6.3 | 0.6.3 (2023-10-30) | Current | Project effectively in maintenance mode. No CVEs since CVE-2023-30798 (fixed in 0.6.3). |
| flask-compress | >=1.14 | 1.24 (2026-03-31) | 10 minor | Many releases added Brotli/Zstandard support, ASGI compatibility, streaming response fix. No CVEs but bump recommended. |
| Werkzeug | >=3.0.0 | 3.1.8 | 1 minor | **Important**: CVE-2024-49767 (resource exhaustion via multipart, fixed in 3.0.6) and CVE-2024-34069 (debugger PIN, fixed in 3.0.3). Floor `>=3.0.0` allows vulnerable installs. Bump to `>=3.0.6` at minimum, ideally `>=3.1.0`. |
| requests | >=2.31.0 | 2.34.2 | 3 minor | CVE-2024-35195 (Session verify=False persistence bug, fixed in 2.32.0). Floor `>=2.31.0` is vulnerable. Bump to `>=2.32.4`. |
| python-dotenv | >=1.0.0 | 1.2.2 (2026-03-01) | 2 minor | Adds Python 3.14 free-threaded support, better multiline handling. No CVEs. |
| google-api-python-client | >=2.100.0 | 2.196.0 | ~96 minor | In maintenance mode — frequent generated-client updates. No outstanding CVEs. Worth bumping for newer Gmail API surface coverage. |
| google-auth-httplib2 | >=0.1.1 | 0.2.0 | 1 minor | Minor refactor; no CVEs. |
| google-auth-oauthlib | >=1.1.0 | 1.4.0 (2026-05-07) | 3 minor | Drops Python <3.10. No CVEs but stale floor will pull old `google-auth` transitively. |
| pywebpush | >=2.0.0 | 2.3.0 (2026-02-09) | 1 minor | 2.x line modern. No CVEs. |
| cryptography | >=41.0.0 | 48.0.0 | ~7 majors | **Critical**: 41.x has multiple CVEs (CVE-2023-49083 NULL deref, CVE-2023-50782 Bleichenbacher timing, CVE-2024-26130 NULL deref, CVE-2024-12797 OpenSSL RH-bundled). Floor `>=41.0.0` is severely outdated. Bump floor to `>=43.0.1` (last with OpenSSL 3.0 LTS) or current `>=46.0.0`. |
| waitress | >=3.0.0 | 3.0.2 (2024-11-16) | Patch | CVE-2024-49768 (request smuggling via HTTP pipelining, fixed in 3.0.1) and trusted-proxy header fix in 3.0.2. Floor `>=3.0.0` is vulnerable. Bump to `>=3.0.2`. |
| pytest | >=7.0 | 8.x line current | 1 major | Pytest 8 dropped Python <3.8 and changed fixture scoping defaults. Floor is fine for now; test code should be checked before upgrade. |

Transitive (not pinned directly but pulled by Flask/Flask-SQLAlchemy):

| Package | Latest stable | Notes |
|---|---|---|
| Jinja2 | 3.1.6 (2025-03-05) | 3.1.5/3.1.6 fixed CVE-2024-56326 + CVE-2025-27516 (sandbox escape via `attr` filter / `|attr`). Anything `<3.1.5` is vulnerable. Pin should be added: `Jinja2>=3.1.6`. |
| SQLAlchemy | 2.0.49 (2025-01-09) | Flask-SQLAlchemy 3.1.1 pulls SQLAlchemy 2.x. No active CVEs. |
| Alembic | 1.18.4 | Pulled via Flask-Migrate. No CVEs. |

## Recommendations

Top upgrades to apply, in priority order:

1. **cryptography → `>=46.0.0`** (CRITICAL). The floor `>=41.0.0` allows installs with at least four known CVEs, including two NULL-pointer derefs and a Bleichenbacher timing oracle. `pywebpush` and `google-auth-oauthlib` both depend on it; both happily accept the newer line. This is the single most important bump.

2. **Werkzeug → `>=3.0.6`** (HIGH). CVE-2024-34069 (debugger PIN bypass) and CVE-2024-49767 (multipart DoS) are both fixed by 3.0.6. Even though the app runs Waitress in production, the dev server is used locally and the debugger CVE matters there.

3. **requests → `>=2.32.4`** (MEDIUM). CVE-2024-35195 leaks `verify=False` state across a Session. The Ollama service uses a fresh `requests.post()` per call (no Session reuse), so impact is low, but bumping is trivial and removes the noisy advisory.

4. **waitress → `>=3.0.2`** (MEDIUM). Request-smuggling CVE in 3.0.0 is directly relevant since Waitress is the production WSGI server behind Cloudflare. CVE-2024-49768 fix is in 3.0.1; 3.0.2 adds the trusted-proxy hardening.

5. **Pin Jinja2 explicitly → `Jinja2>=3.1.6`** (MEDIUM). Two sandbox-escape CVEs in 2025 (CVE-2024-56326 / CVE-2025-27516) affect anything below 3.1.5. Flask 3.x's floor is `Jinja2>=3.1.2` so the current `>=3.0.0` flask pin can resolve a vulnerable Jinja2.

Lower-priority cleanups (no CVEs, just staleness): `flask>=3.1.0`, `flask-compress>=1.24`, `flask-migrate>=4.1.0`, `pywebpush>=2.3.0`, `python-dotenv>=1.2.0`, `google-auth-oauthlib>=1.4.0`.

Suggested updated security-relevant block for `requirements.txt`:

```
flask>=3.1.0
Werkzeug>=3.0.6
Jinja2>=3.1.6
requests>=2.32.4
cryptography>=46.0.0
waitress>=3.0.2
```

After bumping, regenerate the install (`pip install -U -r requirements.txt`) and run the pytest suite to catch any 2.x→2.x minor breakage (most likely from Werkzeug's stricter cookie parsing and requests' Session changes).

## Ollama API check

`services/ai_service.py` uses:
- `GET {ollama_url}/api/tags` — list installed models. **Current**, still supported in 2026.
- `POST {ollama_url}/api/chat` — primary path for `generate_response`, `_call_chat_api`, model preload. Uses `{ model, messages: [{role, content}], stream: false, options: { temperature, num_predict } }`. **Current and idiomatic** — this is the recommended endpoint for multi-turn / role-based prompting.
- `POST {ollama_url}/api/generate` — used only in `extract_correction_topic` with `{ model, prompt, stream: false, options: {...} }`. **Current**; `/api/generate` is the single-prompt (non-chat) endpoint and is still supported.

Findings:
- Field shapes match the Ollama spec as of 2026: `model`, `messages`, `stream`, `options.temperature`, `options.num_predict` are all current names.
- Response parsing reads `result['message']['content']` for `/api/chat` (correct) and falls back to `result['response']` (correct, that's the `/api/generate` shape — useful for resilience).
- `eval_count` logging is correct — Ollama still returns this field for token-count telemetry.
- No use of the newer `tools` / function-calling field on `/api/chat`, no use of `keep_alive`, no use of structured-output `format: "json"` parameter. None of these are required, but `format: 'json'` could replace the brittle ```json``` strip-and-regex fallback in `extract_guest_info` and `extract_knowledge_from_message` — Ollama will then guarantee parseable JSON from compatible models. Worth considering as a follow-up.
- No deprecated endpoints in use. The legacy `/api/embeddings` path is not touched (project uses keyword KB, not embeddings).

Net: the Ollama HTTP integration is up-to-date and idiomatic. The only opportunity is the optional `format: 'json'` flag for extraction calls.
