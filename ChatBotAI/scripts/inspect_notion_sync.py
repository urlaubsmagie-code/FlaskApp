"""Read-only preview / apply for the Notion knowledge-base sync.

Lists the pages under the configured handbook hub and shows, per page, whether
the safety scrubber would BLOCK it or how the mapper would turn it into
KnowledgeEntry / ReplyTemplate rows. Writes NOTHING in preview mode. Pass
--apply to run a real sync (NotionService.sync) that persists to the DB.

    cd C:\\Users\\admin\\Documents\\FlaskApp
    set PYTHONIOENCODING=utf-8
    python -m ChatBotAI.scripts.inspect_notion_sync          # read-only preview
    python -m ChatBotAI.scripts.inspect_notion_sync --apply  # write to DB

Requires the app to be configured with a Notion integration token + root page
id in Settings (AISettings: notion_integration_token, notion_root_page_id,
notion_sync_enabled). Without those it prints a clear "not configured" notice.
"""
import sys

from ChatBotAI.app import create_app
from ChatBotAI.services.notion_service import get_notion_service, get_notion_config
from ChatBotAI.services import notion_scrubber as scrub
from ChatBotAI.services import notion_mapper as mapper


def _preview(cfg):
    """Read-only walk: list pages, show block/map decision per page. No DB writes."""
    from ChatBotAI.services.notion_client import NotionClient
    client = NotionClient(token=cfg['token'])
    try:
        page_ids = client.list_descendant_pages(cfg['root_page_id'])
    except Exception as e:
        print(f"Failed to list pages under root {cfg['root_page_id']}: {e}")
        return

    print(f"Found {len(page_ids)} page(s) under the hub. (read-only preview)\n")
    blocked = kept = templates = 0
    for pid in page_ids:
        try:
            page = client.get_page(pid)
        except Exception as e:
            print(f"  [ERROR] {pid}: {e}")
            continue
        title = page.get('title') or '(untitled)'
        if pid in cfg['force_exclude_ids'] or (
                pid not in cfg['force_include_ids']
                and scrub.is_blocked_page(title, page.get('text', ''), cfg['block_keywords'])):
            blocked += 1
            print(f"  BLOCKED  {title}")
            continue
        if mapper.is_template_page(page):
            templates += 1
            print(f"  TEMPLATE {title}")
            continue
        entries = mapper.page_to_kb_entries(page, {})
        # count entries whose value survives scrubbing non-empty
        usable = sum(1 for e in entries if scrub.scrub_value(e['value']).strip())
        kept += usable
        print(f"  KB x{usable:<2} {title}")
    print(f"\nSummary: {kept} KB entries, {templates} templates, {blocked} pages blocked.")


def main():
    app = create_app()
    with app.app_context():
        cfg = get_notion_config()
        if not cfg['token'] or not cfg['root_page_id']:
            print("Notion sync not configured — set notion_integration_token and "
                  "notion_root_page_id in Settings (and enable it) first.")
            return

        if '--apply' in sys.argv:
            if not cfg['enabled']:
                print("notion_sync_enabled is false — enable it in Settings before --apply.")
                return
            print("APPLY mode — running a real sync (writes to DB)...\n")
            stats = get_notion_service().sync()
            print("Sync stats:")
            for k, v in stats.items():
                print(f"  {k}: {v}")
        else:
            print("PREVIEW mode (no DB writes). Re-run with --apply to persist.\n")
            _preview(cfg)


if __name__ == "__main__":
    main()
