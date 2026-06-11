"""Prompt template loader.

Wraps a standalone Jinja2 Environment that loads prompt templates from
the project's `prompts/` directory. Standalone (not Flask-bound) so it
works in background sync threads as well as HTTP request contexts.

Templates are cached in memory; in development, set
PROMPT_DEV_AUTO_RELOAD=true so edits are picked up without a restart.
"""

import logging
import os
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

_auto_reload = os.environ.get("PROMPT_DEV_AUTO_RELOAD", "false").lower() == "true"

_env = Environment(
    loader=FileSystemLoader(str(PROMPT_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    auto_reload=_auto_reload,
)


def load_prompt(name: str, tier: str, **context) -> str:
    """Render a prompt template.

    Args:
        name: Template basename without .txt (e.g. 'guest_reply').
        tier: Subdirectory ('compact', 'rich', 'shared', 'shared/tone').
        **context: Variables passed to the Jinja2 template.

    Returns:
        Rendered string.

    Raises:
        TemplateNotFound if the file does not exist.
    """
    template_path = f"{tier}/{name}.txt"
    try:
        template = _env.get_template(template_path)
    except TemplateNotFound:
        logger.error("Prompt template not found: %s", template_path)
        raise
    return template.render(**context)


def list_available_tones() -> List[str]:
    """Return the basenames of every tone file under shared/tone/."""
    tone_dir = PROMPT_DIR / "shared" / "tone"
    if not tone_dir.is_dir():
        return []
    return sorted(p.stem for p in tone_dir.glob("*.txt"))
