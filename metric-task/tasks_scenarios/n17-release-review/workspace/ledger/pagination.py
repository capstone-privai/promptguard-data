"""Query parameters for listing endpoints."""


def window(query, settings):
    """(offset, limit) for ?offset=&limit=. Raises ValueError for values the API reference calls invalid."""
    offset = int(query.get("offset", "0"))
    limit = int(query.get("limit", settings.page_size_default))
    if offset < 0 or limit < 1:
        raise ValueError("offset must not be negative and limit must be positive")
    return offset, min(limit, settings.page_size_max)
