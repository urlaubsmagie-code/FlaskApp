"""
Full-text search utilities using SQLite FTS5.
Provides ranked search across messages, guest names, and conversation subjects.
"""

from sqlalchemy import text
from ..models import db, Message, Conversation, Guest


def check_fts5_available():
    """Verify FTS5 is available in the SQLite library."""
    try:
        db.session.execute(text("SELECT * FROM message_fts LIMIT 0"))
        return True
    except Exception:
        return False


def search_messages(query_text, limit=50, conversation_ids=None):
    """
    Search messages using FTS5 with BM25 ranking.

    Args:
        query_text: Search query (supports FTS5 syntax: AND, OR, NOT, "phrases")
        limit: Maximum results to return
        conversation_ids: Optional list of conversation IDs to filter results

    Returns:
        List of dicts with message data, conversation info, and relevance score
    """
    if not query_text or not query_text.strip():
        return []

    # Escape special FTS5 characters and prepare query
    # FTS5 uses * for prefix matching, we add it for partial word matching
    clean_query = query_text.strip()

    # Build the SQL query with optional conversation filter
    filter_clause = ""
    params = {'query': clean_query, 'limit': limit}

    if conversation_ids:
        filter_clause = "AND m.conversation_id IN :conv_ids"
        params['conv_ids'] = tuple(conversation_ids)

    sql = text(f"""
        SELECT
            m.id,
            m.content,
            m.sender_type,
            m.sent_at,
            m.conversation_id,
            c.subject,
            c.platform,
            g.id as guest_id,
            g.name as guest_name,
            p.name as property_name,
            bm25(message_fts) as relevance
        FROM message_fts
        JOIN message m ON message_fts.rowid = m.id
        JOIN conversation c ON m.conversation_id = c.id
        JOIN guest g ON c.guest_id = g.id
        LEFT JOIN property p ON c.property_id = p.id
        WHERE message_fts MATCH :query
        {filter_clause}
        ORDER BY bm25(message_fts)
        LIMIT :limit
    """)

    try:
        results = db.session.execute(sql, params).fetchall()
        return [
            {
                'message_id': row.id,
                'content': row.content,
                'sender_type': row.sender_type,
                'sent_at': row.sent_at if isinstance(row.sent_at, str) else (row.sent_at.isoformat() if row.sent_at else None),
                'conversation_id': row.conversation_id,
                'subject': row.subject,
                'platform': row.platform,
                'guest_id': row.guest_id,
                'guest_name': row.guest_name,
                'property_name': row.property_name,
                'relevance': row.relevance
            }
            for row in results
        ]
    except Exception as e:
        # Log error and return empty results (graceful degradation)
        import logging
        logging.getLogger(__name__).error(f"Search error: {e}")
        return []


def search_by_guest_name(name_query, limit=20):
    """
    Search conversations by guest name only.

    Args:
        name_query: Guest name to search for
        limit: Maximum results

    Returns:
        List of conversation dicts with guest info
    """
    if not name_query or not name_query.strip():
        return []

    # Use FTS5 column filter to search only guest_name field
    sql = text("""
        SELECT DISTINCT
            c.id as conversation_id,
            c.subject,
            c.platform,
            c.status,
            c.is_read,
            c.updated_at,
            g.id as guest_id,
            g.name as guest_name,
            g.email as guest_email
        FROM message_fts
        JOIN message m ON message_fts.rowid = m.id
        JOIN conversation c ON m.conversation_id = c.id
        JOIN guest g ON c.guest_id = g.id
        WHERE message_fts MATCH 'guest_name:' || :query
        ORDER BY c.last_message_at DESC
        LIMIT :limit
    """)

    try:
        results = db.session.execute(sql, {'query': name_query.strip(), 'limit': limit}).fetchall()
        return [
            {
                'conversation_id': row.conversation_id,
                'subject': row.subject,
                'platform': row.platform,
                'status': row.status,
                'is_read': row.is_read,
                'updated_at': row.updated_at if isinstance(row.updated_at, str) else (row.updated_at.isoformat() if row.updated_at else None),
                'guest_id': row.guest_id,
                'guest_name': row.guest_name,
                'guest_email': row.guest_email
            }
            for row in results
        ]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Guest name search error: {e}")
        return []


def rebuild_search_index():
    """
    Rebuild the FTS5 index from scratch.
    Use after bulk data changes or if index becomes corrupt.
    """
    try:
        # Clear and repopulate since we're not using external content
        db.session.execute(text("DELETE FROM message_fts"))
        db.session.execute(text("""
            INSERT INTO message_fts(rowid, content, guest_name, subject)
            SELECT m.id, m.content, g.name, c.subject
            FROM message m
            JOIN conversation c ON m.conversation_id = c.id
            JOIN guest g ON c.guest_id = g.id
        """))
        db.session.commit()
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Index rebuild error: {e}")
        db.session.rollback()
        return False


def get_search_snippet(query_text, message_id, around=10):
    """
    Get a snippet of text around the search match for display.

    Args:
        query_text: Original search query
        message_id: Message ID to get snippet for
        around: Number of tokens to include around match

    Returns:
        Snippet string with match highlighted using <mark> tags
    """
    sql = text("""
        SELECT snippet(message_fts, 0, '<mark>', '</mark>', '...', :around) as snippet
        FROM message_fts
        WHERE message_fts.rowid = :message_id
        AND message_fts MATCH :query
    """)

    try:
        result = db.session.execute(sql, {
            'query': query_text,
            'message_id': message_id,
            'around': around
        }).fetchone()
        return result.snippet if result else None
    except Exception:
        return None
