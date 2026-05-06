"""Prompt tier detection.

Decides whether a given model should use the compact or rich prompt template.
Rule: cloud models (suffix '-cloud') or local models >= 70B are 'rich'.
Everything else is 'compact'.
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

RICH_SIZE_THRESHOLD_B = 70
_VALID_TIERS = {"compact", "rich"}


def detect_tier(model_name: Optional[str]) -> str:
    """Return 'compact' or 'rich' for the given Ollama model name.

    Examples:
        detect_tier('gemma2:9b')           -> 'compact'
        detect_tier('gpt-oss:120b-cloud')  -> 'rich'
        detect_tier('llama3.1:70b')        -> 'rich'
        detect_tier(None)                  -> 'compact'

    Override: setting env var FORCE_PROMPT_TIER to 'compact' or 'rich'
    bypasses detection entirely. Used only for debugging.
    """
    forced = os.environ.get("FORCE_PROMPT_TIER", "").strip().lower()
    if forced in _VALID_TIERS:
        return forced

    if not model_name:
        return "compact"

    name = model_name.lower()
    if name.endswith("-cloud"):
        return "rich"

    match = re.search(r":(\d+)b", name)
    if match and int(match.group(1)) >= RICH_SIZE_THRESHOLD_B:
        return "rich"

    return "compact"
