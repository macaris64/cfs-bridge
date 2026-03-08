"""UI utility functions for telemetry JSON viewer pagination."""
from math import ceil
from typing import List, Tuple, Any

ITEMS_PER_PAGE = 10


def page_count(total_items: int) -> int:
    """Return number of pages for total_items with ITEMS_PER_PAGE per page."""
    return max(1, ceil(total_items / ITEMS_PER_PAGE))


def slice_for_page(items: List[Any], page: int) -> List[Any]:
    """Return the sublist of items for the requested page.

    Assumes items are ordered newest-first.
    Page is 1-indexed.
    """
    if page < 1:
        page = 1
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = min(page * ITEMS_PER_PAGE, len(items))
    window = items[start_idx:end_idx]
    seen = set()
    result = []
    for it in window:
        if hasattr(it, "raw_hex") or hasattr(it, "timestamp"):
            key = (getattr(it, "raw_hex", None), getattr(it, "timestamp", None))
        else:
            key = id(it)
        if key in seen:
            continue
        seen.add(key)
        result.append(it)
    return result


def filter_items_by_event(items: List[Any], event_types: List[str]) -> List[Any]:
    """Filter items by their parsed 'type' field.

    - `items` is a newest-first list of telemetry entry objects that may have a
      `.parsed` dict attribute.
    - `event_types` is a list of types to include (e.g. ['evs']) or empty/['all']
      to include everything.
    """
    if not event_types:
        return items
    if "all" in event_types:
        return items

    out = []
    for it in items:
        parsed = getattr(it, "parsed", None) or {}
        typ = parsed.get("type", None)
        if typ in event_types:
            out.append(it)
    return out


def update_page_on_new(total: int, prev_total: int, current_page: int, auto_scroll: bool) -> Tuple[int, int]:
    """Determine the current_page and new prev_total when data changes.

    Legacy auto-scroll behavior removed.
    This function now only ensures the current_page is within valid range
    when the total changes (e.g. total decreased). It returns (new_page, total)
    for storing as last_total.
    """
    pc = page_count(total)
    if current_page > pc:
        return pc, total
    if current_page < 1:
        return 1, total
    return current_page, total

