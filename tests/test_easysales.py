from unittest.mock import patch, MagicMock
from easysales_api import EasySalesAPI


def make_client():
    return EasySalesAPI(token="test-token")


# ---------------------------------------------------------------------------
# calculate_daily_sales
# ---------------------------------------------------------------------------

def test_daily_sales_basic_aggregation():
    client = make_client()
    orders = [
        {"id": 1, "items": [{"sku": "ABC", "quantity": 10, "name": "Product A"}]},
        {"id": 2, "items": [{"sku": "ABC", "quantity": 20, "name": "Product A"}]},
    ]
    result = client.calculate_daily_sales(orders, days_in_period=30)

    assert "ABC" in result
    assert result["ABC"]["total_quantity"] == 30
    assert result["ABC"]["daily_sales"] == 1.0   # 30 / 30
    assert result["ABC"]["order_count"] == 2     # 2 unique orders
    assert result["ABC"]["days_in_period"] == 30


def test_daily_sales_multiple_skus():
    client = make_client()
    orders = [
        {"items": [
            {"sku": "ABC", "quantity": 60, "name": "A"},
            {"sku": "XYZ", "quantity": 30, "name": "X"},
        ]},
    ]
    result = client.calculate_daily_sales(orders, days_in_period=30)

    assert result["ABC"]["daily_sales"] == 2.0   # 60 / 30
    assert result["XYZ"]["daily_sales"] == 1.0   # 30 / 30


def test_daily_sales_skips_zero_and_negative_quantity():
    client = make_client()
    orders = [
        {"items": [
            {"sku": "ABC", "quantity": 0,   "name": "A"},   # zero — skip
            {"sku": "ABC", "quantity": -5,  "name": "A"},   # negative — skip
            {"sku": "ABC", "quantity": 10,  "name": "A"},   # valid
        ]},
    ]
    result = client.calculate_daily_sales(orders, days_in_period=10)

    assert result["ABC"]["total_quantity"] == 10
    assert result["ABC"]["daily_sales"] == 1.0


def test_daily_sales_skips_items_without_sku():
    client = make_client()
    orders = [
        {"items": [
            {"quantity": 50, "name": "No SKU item"},
            {"sku": "ABC",  "quantity": 10, "name": "Has SKU"},
        ]},
    ]
    result = client.calculate_daily_sales(orders, days_in_period=10)

    assert len(result) == 1
    assert "ABC" in result


def test_daily_sales_zero_days_returns_zero_velocity():
    client = make_client()
    orders = [{"items": [{"sku": "ABC", "quantity": 100, "name": "A"}]}]
    result = client.calculate_daily_sales(orders, days_in_period=0)

    assert result["ABC"]["daily_sales"] == 0


def test_daily_sales_empty_orders():
    client = make_client()
    result = client.calculate_daily_sales([], days_in_period=30)
    assert result == {}


def test_order_count_counts_unique_orders_not_line_items():
    """One order with SKU appearing twice → order_count = 1, not 2."""
    client = make_client()
    orders = [
        {"id": 99, "items": [
            {"sku": "ABC", "quantity": 5, "name": "A"},
            {"sku": "ABC", "quantity": 5, "name": "A"},  # same SKU, same order
        ]},
    ]
    result = client.calculate_daily_sales(orders, days_in_period=10)

    assert result["ABC"]["total_quantity"] == 10
    assert result["ABC"]["order_count"] == 1   # one unique order, not two line items


def test_daily_sales_falls_back_to_products_key():
    """Order uses 'products' key instead of 'items'."""
    client = make_client()
    orders = [{"products": [{"sku": "ABC", "quantity": 30, "name": "A"}]}]
    result = client.calculate_daily_sales(orders, days_in_period=30)
    assert result["ABC"]["daily_sales"] == 1.0


# ---------------------------------------------------------------------------
# get_orders — deduplication
# ---------------------------------------------------------------------------

def _mock_page(orders, per_page=50):
    """Build a fake paginated API response."""
    return {"data": orders, "meta": {"per_page": per_page}}


@patch("easysales_api.requests.get")
def test_get_orders_deduplicates_same_id(mock_get):
    """Order with id=1 appearing on two pages must only be counted once."""
    order = {"id": 1, "items": []}

    page1 = MagicMock()
    page1.json.return_value = _mock_page([order])
    page1.raise_for_status = MagicMock()

    page2 = MagicMock()
    page2.json.return_value = _mock_page([order])   # same order again
    page2.raise_for_status = MagicMock()

    page3 = MagicMock()
    page3.json.return_value = _mock_page([])         # empty — stop
    page3.raise_for_status = MagicMock()

    mock_get.side_effect = [page1, page2, page3]

    client = make_client()
    result = client.get_orders(start_date="2026-01-01", end_date="2026-03-01", max_pages=10)

    assert len(result) == 1


@patch("easysales_api.requests.get")
def test_get_orders_stops_on_empty_page(mock_get):
    order = {"id": 1, "items": []}

    page1 = MagicMock()
    page1.json.return_value = _mock_page([order])
    page1.raise_for_status = MagicMock()

    page2 = MagicMock()
    page2.json.return_value = _mock_page([])  # empty
    page2.raise_for_status = MagicMock()

    # page3 should never be called
    mock_get.side_effect = [page1, page2]

    client = make_client()
    result = client.get_orders(start_date="2026-01-01", end_date="2026-03-01", max_pages=10)

    assert len(result) == 1
    assert mock_get.call_count == 2


@patch("easysales_api.requests.get")
def test_get_orders_respects_max_pages(mock_get):
    order_a = {"id": 1, "items": []}
    order_b = {"id": 2, "items": []}

    page = MagicMock()
    page.json.return_value = _mock_page([order_a, order_b])
    page.raise_for_status = MagicMock()

    mock_get.side_effect = [page, page, page]  # 3 identical pages

    client = make_client()
    result = client.get_orders(start_date="2026-01-01", end_date="2026-03-01", max_pages=2)

    assert mock_get.call_count == 2   # stopped at max_pages


# ---------------------------------------------------------------------------
# actual_days calculation in get_sales_data
# ---------------------------------------------------------------------------

@patch("easysales_api.requests.get")
def test_actual_days_is_end_minus_start(mock_get):
    """30-day window: end - start = 30, not 31."""
    empty = MagicMock()
    empty.json.return_value = _mock_page([])
    empty.raise_for_status = MagicMock()
    mock_get.return_value = empty

    client = make_client()
    # patch calculate_daily_sales to capture days_in_period
    captured = {}
    original = client.calculate_daily_sales

    def spy(orders, days_in_period):
        captured["days"] = days_in_period
        return original(orders, days_in_period)

    client.calculate_daily_sales = spy
    client.get_sales_data(start_date="2026-01-01", end_date="2026-01-31")

    assert captured["days"] == 30  # 31 - 1 = 30, not 31
