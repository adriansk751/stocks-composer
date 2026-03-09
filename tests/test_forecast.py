from forecast import InventoryForecast


def calc(stock={}, sales={}, incoming={}, months=[3], safety=0):
    df = InventoryForecast.calculate_requirements(
        stock_data=stock,
        sales_data=sales,
        incoming_data=incoming,
        forecast_months=months,
        safety_stock_percentage=safety
    )
    return df.set_index("SKU")


# ---------------------------------------------------------------------------
# Core formula:  required = (daily_sales * days * safety_mult) - stock - incoming
# ---------------------------------------------------------------------------

def test_basic_requirement():
    stock   = {"ABC": {"quantity": 0,  "name": "A", "unit": "buc"}}
    sales   = {"ABC": {"daily_sales": 1.0, "name": "A"}}
    row = calc(stock, sales, months=[3])
    # 1.0 * 90 * 1.0 - 0 - 0 = 90
    assert row.loc["ABC", "Required 3M"] == 90.0


def test_surplus_is_negative():
    """More stock than needed → negative required (no order needed)."""
    stock = {"ABC": {"quantity": 200, "name": "A", "unit": "buc"}}
    sales = {"ABC": {"daily_sales": 1.0, "name": "A"}}
    row = calc(stock, sales, months=[3])
    # 90 - 200 = -110
    assert row.loc["ABC", "Required 3M"] == -110.0


def test_safety_stock_increases_requirement():
    stock = {"ABC": {"quantity": 0, "name": "A", "unit": "buc"}}
    sales = {"ABC": {"daily_sales": 1.0, "name": "A"}}

    without = calc(stock, sales, months=[3], safety=0).loc["ABC", "Required 3M"]
    with_20 = calc(stock, sales, months=[3], safety=20).loc["ABC", "Required 3M"]

    assert with_20 > without
    assert with_20 == 90 * 1.2  # 108


def test_incoming_reduces_requirement():
    stock    = {"ABC": {"quantity": 0, "name": "A", "unit": "buc"}}
    sales    = {"ABC": {"daily_sales": 1.0, "name": "A"}}
    incoming = {"ABC": 30}
    row = calc(stock, sales, incoming, months=[3])
    # 90 - 0 - 30 = 60
    assert row.loc["ABC", "Required 3M"] == 60.0


def test_multiple_forecast_horizons():
    stock = {"ABC": {"quantity": 0, "name": "A", "unit": "buc"}}
    sales = {"ABC": {"daily_sales": 1.0, "name": "A"}}
    row = calc(stock, sales, months=[3, 6])
    assert row.loc["ABC", "Required 3M"] == 90.0
    assert row.loc["ABC", "Required 6M"] == 180.0


def test_sku_in_sales_but_not_stock():
    """SKU sold but not in stock → current_stock defaults to 0."""
    sales = {"ABC": {"daily_sales": 2.0, "name": "A"}}
    row = calc(sales=sales, months=[3])
    assert row.loc["ABC", "Required 3M"] == 180.0


def test_sku_in_stock_but_not_sales():
    """SKU in stock but never sold → daily_sales = 0, required = -stock."""
    stock = {"ABC": {"quantity": 50, "name": "A", "unit": "buc"}}
    row = calc(stock=stock, months=[3])
    assert row.loc["ABC", "Required 3M"] == -50.0


def test_zero_daily_sales_no_requirement():
    stock = {"ABC": {"quantity": 0, "name": "A", "unit": "buc"}}
    sales = {"ABC": {"daily_sales": 0.0, "name": "A"}}
    row = calc(stock, sales, months=[3])
    assert row.loc["ABC", "Required 3M"] == 0.0


# ---------------------------------------------------------------------------
# filter_active_products
# ---------------------------------------------------------------------------

def test_filter_removes_low_sales():
    stock = {
        "A": {"quantity": 0, "name": "A", "unit": "buc"},
        "B": {"quantity": 0, "name": "B", "unit": "buc"},
    }
    sales = {
        "A": {"daily_sales": 0.005, "name": "A"},
        "B": {"daily_sales": 2.0,   "name": "B"},
    }
    df = InventoryForecast.calculate_requirements(stock, sales, {}, [3])
    filtered = InventoryForecast.filter_active_products(df, min_daily_sales=0.01)

    assert "B" in filtered["SKU"].values
    assert "A" not in filtered["SKU"].values


# ---------------------------------------------------------------------------
# get_critical_items
# ---------------------------------------------------------------------------

def test_critical_items_only_positive_required():
    stock = {
        "NEED": {"quantity": 0,   "name": "N", "unit": "buc"},
        "OK":   {"quantity": 999, "name": "O", "unit": "buc"},
    }
    sales = {
        "NEED": {"daily_sales": 1.0, "name": "N"},
        "OK":   {"daily_sales": 1.0, "name": "O"},
    }
    df = InventoryForecast.calculate_requirements(stock, sales, {}, [3])
    critical = InventoryForecast.get_critical_items(df, horizon_months=3)

    assert "NEED" in critical["SKU"].values
    assert "OK" not in critical["SKU"].values
