from ground_station.telemetry import ui_utils


def test_page_count_and_slicing():
    items = list(range(35))
    total = len(items)
    pc = ui_utils.page_count(total)
    assert pc == 4

    p1 = ui_utils.slice_for_page(items, 1)
    assert p1 == items[0:10]

    p4 = ui_utils.slice_for_page(items, 4)
    assert p4 == items[30:40]


def test_slice_for_page_handles_zero_page():
    items = list(range(15))
    p0 = ui_utils.slice_for_page(items, 0)
    assert p0 == items[0:10]


def test_slice_for_page_deduplicates_window():
    class Item:
        def __init__(self, raw_hex, timestamp):
            self.raw_hex = raw_hex
            self.timestamp = timestamp

    items = [Item("a", 1), Item("b", 2), Item("c", 3)] + [Item("d", i) for i in range(4, 14)]
    items[11] = Item("d", 10)
    page2 = ui_utils.slice_for_page(items, 2)
    keys = [(it.raw_hex, it.timestamp) for it in page2]
    assert len(keys) == len(set(keys))


def test_update_page_on_new_caps_only():
    current_page = 2
    new_page, last_total = ui_utils.update_page_on_new(total=25, prev_total=20, current_page=current_page, auto_scroll=False)
    assert new_page == current_page
    assert last_total == 25

    new_page, last_total = ui_utils.update_page_on_new(total=5, prev_total=50, current_page=10, auto_scroll=False)
    assert new_page == ui_utils.page_count(5)
    assert last_total == 5


def test_filter_items_by_event_and_pagination():
    class Item:
        def __init__(self, parsed, timestamp):
            self.parsed = parsed
            self.timestamp = timestamp

    evs_items = [Item({"type": "evs", "id": i}, i) for i in range(15, 5, -1)]
    tlm_items = [Item({"type": "tlm", "id": i}, i) for i in range(5, 0, -1)]
    items = evs_items + tlm_items

    filtered = ui_utils.filter_items_by_event(items, ["evs"])
    assert all((getattr(it, "parsed") or {}).get("type") == "evs" for it in filtered)
    page1 = ui_utils.slice_for_page(filtered, 1)
    assert len(page1) == min(len(filtered), ui_utils.ITEMS_PER_PAGE)

