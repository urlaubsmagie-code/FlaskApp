# Coding Conventions

**Analysis Date:** 2026-02-17

## Naming Patterns

**Files:**
- Lowercase snake_case for all Python modules: `ai_service.py`, `memory_service.py`, `message_router.py`
- Services live in `services/` subdirectory with `_service.py` suffix
- Utility modules live in `utils/` subdirectory

**Classes:**
- PascalCase for all class names: `AIService`, `MemoryService`, `MessageRouter`, `Guest`, `GuestDetail`, `Conversation`, `Message`, `Property`, `AISettings`
- SQLAlchemy models use PascalCase: `Guest`, `Conversation`, `Message`
- Service classes use PascalCase with "Service" suffix: `AIService`, `MemoryService`, `GmailService`

**Functions/Methods:**
- lowercase snake_case for all functions and methods: `process_incoming_message()`, `find_or_create_guest()`, `get_guest_profile()`
- Private/internal methods prefixed with single underscore: `_get_services()`, `_find_or_create_guest()`, `_store_message()`, `_generate_ai_response()`, `_build_response_prompt()`, `_empty_extraction()`
- Module-level init functions follow pattern `init_<service_name>()`: `init_ai_service()`, `init_memory_service()`
- Module-level getter functions follow pattern `get_<service_name>()`: `get_ai_service()`, `get_memory_service()`, `get_message_router()`

**Variables:**
- lowercase snake_case: `guest_id`, `platform_id`, `message_content`, `ai_service`
- Module-level singleton instances prefixed with underscore: `_ai_service`, `_memory_service`, `_message_router`
- Boolean flags use descriptive names: `is_processed`, `ai_enabled`, `pet_friendly`, `auto_respond`

**Constants/Config:**
- UPPER_SNAKE_CASE for config class attributes: `SQLALCHEMY_DATABASE_URI`, `OLLAMA_URL`, `OLLAMA_MODEL`
- Database table names use lowercase snake_case in `__tablename__`: `'guest'`, `'guest_detail'`, `'conversation'`, `'message'`, `'ai_settings'`

**Routes:**
- Flask route functions use snake_case with descriptive names: `api_get_conversations()`, `api_send_message()`, `api_generate_ai_response()`
- API route functions prefixed with `api_`: `api_get_guest()`, `api_add_guest_detail()`
- Webhook route functions prefixed with `webhook_`: `webhook_gmail()`, `webhook_whatsapp()`
- Page route functions use descriptive names without prefix: `index()`, `conversation_view()`, `guest_profile()`, `settings()`

## Code Style

**Formatting:**
- No automated formatter configured (no `.prettierrc`, `pyproject.toml` with black config, or similar)
- Indentation: 4 spaces (standard Python)
- Line length: not enforced by tooling but kept reasonable (~100 chars)
- Blank lines: two blank lines between top-level functions/classes; one blank line between methods

**Linting:**
- No linter configuration file detected (no `.flintrc`, `pyproject.toml`, `setup.cfg`)
- Code follows PEP 8 conventions manually

**Docstrings:**
- Module-level docstrings present on all files: `"""Module description\n..."""`
- Class docstrings present on all classes
- Method docstrings present on all public methods
- Docstring format uses Args/Returns sections for complex methods:
  ```python
  def process_incoming_message(self, platform: str, ...) -> Dict[str, Any]:
      """
      Process an incoming message from any platform.

      Args:
          platform: Source platform (email, whatsapp, airbnb, booking)
          ...

      Returns:
          Dict with processing results including any AI response
      """
  ```

## Import Organization

**Order:**
1. Standard library imports (`os`, `json`, `logging`, `datetime`, `typing`, `pathlib`)
2. Third-party imports (`flask`, `flask_sqlalchemy`, `requests`)
3. Internal relative imports (`.models`, `.config`, `.services.ai_service`)

**Pattern in service files:**
```python
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from ..models import db, Guest, GuestDetail, Message
from .ai_service import get_ai_service
```

**Pattern in routes.py:**
```python
from flask import render_template, request, jsonify, redirect, url_for
from datetime import datetime

from . import chatbot_bp
from .models import db, Guest, GuestDetail, Conversation, Message, Property, AISettings
from .services.ai_service import get_ai_service
from .services.memory_service import get_memory_service
```

**Late imports:** Some imports are deferred inside functions for circular dependency avoidance:
```python
# In routes.py - inside route functions
from .services.message_router import get_message_router
from .services.gmail_service import get_gmail_service
```

**Path Aliases:**
- Not used. All imports use relative paths within the package.

## Type Hints

**Usage:** Type hints used throughout service files, not in routes.py or models.py.
```python
def find_or_create_guest(
    self,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    platform: Optional[str] = None,
    platform_id: Optional[str] = None,
    name: Optional[str] = None
) -> Guest:
```

**Imports:** `from typing import Optional, Dict, List, Any` — use these types. Python 3.9+ built-in generics (`list[str]`, `dict[str, Any]`) are not used yet.

## Error Handling

**Pattern:** All service methods use `try/except Exception` with rollback on database errors:
```python
try:
    # ... database operations
    db.session.commit()
    return True
except Exception as e:
    logger.error(f"Error storing detail: {e}")
    db.session.rollback()
    return False
```

**Result dictionaries:** Service methods return structured dicts rather than raising exceptions:
```python
result = {
    'success': False,
    'guest_id': None,
    'conversation_id': None,
    'message_id': None,
    'ai_response': None,
    'error': None
}
# ... operations ...
result['success'] = True
return result
```

**HTTP error responses:** Routes return `jsonify({'error': '...'})` with appropriate HTTP status codes:
```python
if not data or 'content' not in data:
    return jsonify({'error': 'Content is required'}), 400

if not ai_service:
    return jsonify({'error': 'AI service not available'}), 503
```

**Memory extraction failures:** Non-critical failures (memory extraction, AI responses) are caught and logged as warnings, not propagated:
```python
try:
    self.memory_service.process_message_for_memory(message)
except Exception as e:
    logger.warning(f"Memory extraction failed: {e}")
```

## Logging

**Framework:** Python's built-in `logging` module.

**Setup:** Each module creates its own logger at module level:
```python
logger = logging.getLogger(__name__)
```

**Configuration:** Configured in `app.py` `create_app()` at startup:
```python
logging.basicConfig(
    level=logging.DEBUG if app.config.get('DEBUG') else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

**Usage patterns:**
- `logger.debug()` — verbose tracing (e.g., "Message {id} already processed", "Duplicate detail skipped")
- `logger.info()` — successful operations (e.g., "Guest identified: {id}", "Message stored: {id}")
- `logger.warning()` — recoverable failures (e.g., "Ollama connection failed", "Memory extraction failed")
- `logger.error()` — unrecoverable errors (e.g., database errors, request failures)

**f-strings in log messages:** Always used for interpolation:
```python
logger.info(f"Guest identified: {guest.id} ({guest.name or guest.email or 'Unknown'})")
logger.error(f"Error processing message {message.id} for memory: {e}")
```

## Comments

**Section separators:** Large files (`routes.py`) use comment blocks to organize sections:
```python
# ============================================================================
# PAGE ROUTES (HTML Templates)
# ============================================================================
```

**Inline comments:** Used to explain non-obvious business logic:
```python
# AI messages don't need memory extraction
# Owners often mention guest details in their responses
# Try to find by email first (most reliable)
```

## Function Design

**Size:** Methods kept focused on single responsibility. Helper private methods used to break out sub-steps (e.g., `_find_or_create_guest()`, `_store_message()`, `_generate_ai_response()`).

**Parameters:** Keyword arguments with defaults for optional parameters. Long parameter lists formatted one-per-line:
```python
def process_incoming_message(
        self,
        platform: str,
        platform_conversation_id: str,
        sender_email: Optional[str] = None,
        sender_phone: Optional[str] = None,
        ...
) -> Dict[str, Any]:
```

**Return values:** Consistent pattern — service methods return bool (simple CRUD), Optional[T] (lookups), or Dict[str, Any] (complex operations). Models return `to_dict()` dicts for serialization.

## Model Design

**`to_dict()` method:** Required on every SQLAlchemy model. Converts all columns to a JSON-serializable dictionary. DateTime fields always use `.isoformat()` with None guard:
```python
'created_at': self.created_at.isoformat() if self.created_at else None
```

**`__repr__()` method:** Required on every model. Format: `<ClassName field: value>`:
```python
def __repr__(self):
    return f'<Guest {self.id}: {self.name or self.email or "Unknown"}>'
```

**`@property` decorators:** Used for computed attributes on models:
```python
@property
def last_message(self):
    """Get the most recent message in this conversation"""
    return self.messages.order_by(Message.sent_at.desc()).first()
```

**`@classmethod` on models:** Used for query helpers on `AISettings`:
```python
@classmethod
def get(cls, key, default=None):
    setting = cls.query.filter_by(key=key).first()
    return setting.value if setting else default
```

## Service Singleton Pattern

All services follow this exact pattern:

```python
# Module-level private instance
_service_name: Optional[ServiceClass] = None

def init_service_name(app=None) -> ServiceClass:
    """Initialize the service"""
    global _service_name
    _service_name = ServiceClass(...)
    logger.info("Service initialized")
    return _service_name

def get_service_name() -> Optional[ServiceClass]:
    """Get the current service instance"""
    return _service_name
```

Services are initialized in `app.py`'s `create_app()` and retrieved via `get_*_service()` in routes and other services.

## Blueprint Registration

Routes registered via blueprint `chatbot_bp` defined in `__init__.py`. All routes use `@chatbot_bp.route(...)` decorator. URL prefix `/chatbot` applied at blueprint level.

---

*Convention analysis: 2026-02-17*
