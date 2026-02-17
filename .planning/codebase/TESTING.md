# Testing Patterns

**Analysis Date:** 2026-02-17

## Test Framework

**Runner:**
- No test framework currently installed or configured
- `requirements.txt` has pytest and pytest-flask commented out:
  ```
  # pytest>=7.4.0
  # pytest-flask>=1.3.0
  ```
- No `pytest.ini`, `setup.cfg`, `pyproject.toml`, or `conftest.py` found

**Assertion Library:**
- None configured

**Run Commands:**
```bash
# Install test dependencies first (currently commented out in requirements.txt)
pip install pytest pytest-flask

# Then run (no test files exist yet)
pytest

# With coverage
pip install pytest-cov
pytest --cov=ChatBotAI
```

## Test File Organization

**Location:**
- No test files exist in the codebase
- No `tests/` directory exists
- No `*.test.py` or `*_test.py` files found

**Recommended naming convention (based on codebase patterns):**
- Co-locate tests in a `tests/` directory at the package root
- Match test file names to source files: `tests/test_ai_service.py`, `tests/test_memory_service.py`

**Recommended structure:**
```
ChatBotAI/
├── tests/
│   ├── conftest.py          # Shared fixtures and app factory
│   ├── test_models.py       # Model unit tests
│   ├── test_ai_service.py   # AIService unit tests
│   ├── test_memory_service.py  # MemoryService unit tests
│   ├── test_message_router.py  # MessageRouter integration tests
│   └── test_routes.py       # Route/API integration tests
```

## Test Infrastructure Notes

**TestingConfig exists** in `config.py` at `C:\Users\admin\Documents\FlaskApp\ChatBotAI\config.py`:
```python
class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
```

This configuration is ready to use with pytest-flask. The in-memory SQLite database means tests run against a clean DB each time.

**App factory available** at `C:\Users\admin\Documents\FlaskApp\ChatBotAI\app.py`:
```python
def create_app(config_class=None):
    """Application factory for ChatBotAI"""
```

Pass `TestingConfig` to `create_app()` in test fixtures.

## Recommended Test Structure

**Suite organization for new tests:**
```python
# tests/conftest.py
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import TestingConfig
from ChatBotAI.models import db as _db

@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def db(app):
    return _db
```

**Unit test pattern for services:**
```python
# tests/test_memory_service.py
import pytest
from unittest.mock import MagicMock, patch
from ChatBotAI.services.memory_service import MemoryService

class TestMemoryService:
    def test_store_detail_new(self, app, db):
        # Arrange: create guest first
        # Act: call store_detail
        # Assert: verify GuestDetail exists in db
        pass

    def test_store_detail_duplicate_skipped(self, app, db):
        # Assert returns False for exact duplicate
        pass

    def test_get_guest_profile_empty(self, app, db):
        # Assert empty dict for unknown guest
        pass
```

**Route test pattern:**
```python
# tests/test_routes.py
class TestAPIRoutes:
    def test_get_conversations_empty(self, client):
        response = client.get('/chatbot/api/conversations')
        assert response.status_code == 200
        data = response.get_json()
        assert data['conversations'] == []
        assert data['total'] == 0

    def test_send_message_missing_content(self, client):
        response = client.post(
            '/chatbot/api/conversations/999/messages',
            json={}
        )
        assert response.status_code == 400
        assert 'error' in response.get_json()
```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Primary mocking targets:**
- `AIService` — avoid real HTTP calls to Ollama
- `requests.post` / `requests.get` — mock Ollama API responses
- Gmail OAuth flow — mock Google API credentials

**Recommended mocking patterns:**
```python
# Mock AIService Ollama calls
from unittest.mock import patch, MagicMock

def test_extract_guest_info(app):
    with patch('ChatBotAI.services.ai_service.requests.post') as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {'response': '{"guest_name": "John", "family_members": []}'}
        )
        service = AIService()
        result = service.extract_guest_info("Hello, my name is John")
        assert result['guest_name'] == 'John'
```

**What to mock:**
- All external HTTP requests (`requests.post`, `requests.get` to Ollama)
- Gmail API calls (Google API client)
- `datetime.utcnow()` when testing timestamp-dependent logic

**What NOT to mock:**
- SQLAlchemy database operations (use in-memory SQLite via `TestingConfig`)
- Flask routing (use `app.test_client()`)
- Internal service logic (test the real implementation)

## Fixtures and Factories

**Test Data:** No fixture factory exists. Create data directly using models:
```python
# Recommended pattern for test data creation
from ChatBotAI.models import db, Guest, Conversation, Message

def create_test_guest(db, name="Test Guest", email="test@example.com"):
    guest = Guest(name=name, email=email)
    db.session.add(guest)
    db.session.commit()
    return guest

def create_test_conversation(db, guest, platform="email"):
    conv = Conversation(
        guest_id=guest.id,
        platform=platform,
        platform_id=f"test-conv-{guest.id}",
        status='active',
        ai_enabled=True
    )
    db.session.add(conv)
    db.session.commit()
    return conv
```

**Location:** No fixtures directory exists. Create `tests/conftest.py` for shared fixtures and `tests/factories.py` for object factories.

**Built-in test routes:** The application includes test/demo routes at `/api/test/*` that create sample data without real platform integrations:
- `POST /chatbot/api/test/create-conversation` — creates a single test conversation
- `POST /chatbot/api/test/simulate-message` — simulates incoming guest message
- `POST /chatbot/api/test/bulk-create` — creates 5 sample conversations with diverse data

These routes live in `C:\Users\admin\Documents\FlaskApp\ChatBotAI\routes.py` and are useful for manual testing but should not replace automated tests.

## Coverage

**Requirements:** None enforced — no coverage thresholds configured.

**View Coverage:**
```bash
# Install coverage tool
pip install pytest-cov

# Run with coverage report
pytest --cov=ChatBotAI --cov-report=html

# View in browser
open htmlcov/index.html
```

## Test Types

**Unit Tests:**
- Target: Individual service methods in isolation
- Key candidates: `AIService.extract_guest_info()`, `AIService.generate_guest_response()`, `MemoryService.store_detail()`, `MemoryService.get_guest_profile()`, `MemoryService.find_or_create_guest()`
- Approach: Use `TestingConfig` (in-memory SQLite) + mock external HTTP calls

**Integration Tests:**
- Target: Full request/response cycles through Flask routes
- Key candidates: All `/api/*` endpoints in `routes.py`
- Approach: Use `app.test_client()` with real DB operations against in-memory SQLite

**E2E Tests:**
- Not used

## Current Testing State

**No automated tests exist.** The codebase has:
1. `TestingConfig` class ready in `C:\Users\admin\Documents\FlaskApp\ChatBotAI\config.py` (in-memory SQLite)
2. `create_app()` factory in `C:\Users\admin\Documents\FlaskApp\ChatBotAI\app.py` supporting test config injection
3. Test/demo routes in `C:\Users\admin\Documents\FlaskApp\ChatBotAI\routes.py` (`/api/test/*`) for manual testing
4. pytest/pytest-flask commented out in `C:\Users\admin\Documents\FlaskApp\ChatBotAI\requirements.txt`

## Critical Paths to Test First

In priority order based on business risk:

1. **`MemoryService.store_detail()`** — deduplication logic at `C:\Users\admin\Documents\FlaskApp\ChatBotAI\services\memory_service.py:157`
2. **`MemoryService.find_or_create_guest()`** — cross-platform guest matching at `C:\Users\admin\Documents\FlaskApp\ChatBotAI\services\memory_service.py:282`
3. **`MessageRouter.process_incoming_message()`** — main orchestration at `C:\Users\admin\Documents\FlaskApp\ChatBotAI\services\message_router.py:38`
4. **`AIService.extract_guest_info()`** — JSON parsing with AI response cleanup at `C:\Users\admin\Documents\FlaskApp\ChatBotAI\services\ai_service.py:79`
5. **API routes** — validation and error responses in `C:\Users\admin\Documents\FlaskApp\ChatBotAI\routes.py`

---

*Testing analysis: 2026-02-17*
