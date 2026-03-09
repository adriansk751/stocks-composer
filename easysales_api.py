import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os

logger = logging.getLogger(__name__)


class EasySalesAPI:
    BASE_URL = "https://app.easysales.ro/api/v2"
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def get_orders(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_back: int = 30,
        max_pages: int = 10
    ) -> List[Dict]:
        """
        Retrieve orders from easySales API.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            days_back: Number of days to look back if dates not provided
            max_pages: Maximum number of pages to fetch

        Returns:
            List of orders
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if not start_date:
            start = datetime.now() - timedelta(days=days_back)
            start_date = start.strftime("%Y-%m-%d")

        all_orders = []
        seen_ids = set()

        for page in range(1, max_pages + 1):
            params = {
                "after": start_date,
                "before": end_date,
                "page": page
            }

            try:
                response = requests.get(
                    f"{self.BASE_URL}/orders",
                    params=params,
                    headers=self.headers,
                    timeout=30
                )
                response.raise_for_status()

                data = response.json()

                if isinstance(data, list):
                    for order in data:
                        order_id = order.get("id")
                        if order_id is None or order_id not in seen_ids:
                            if order_id is not None:
                                seen_ids.add(order_id)
                            all_orders.append(order)
                    break
                elif isinstance(data, dict) and "data" in data:
                    page_orders = data["data"]

                    new_orders = []
                    for order in page_orders:
                        order_id = order.get("id")
                        if order_id is None or order_id not in seen_ids:
                            if order_id is not None:
                                seen_ids.add(order_id)
                            new_orders.append(order)

                    all_orders.extend(new_orders)

                    logger.info(f"easySales: fetched page {page}/{max_pages} ({len(new_orders)} new orders, {len(page_orders) - len(new_orders)} duplicates skipped)")

                    if len(page_orders) == 0:
                        break
                else:
                    break

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching orders from easySales (page {page}): {e}")
                break

        logger.info(f"easySales: total orders fetched = {len(all_orders)}")

        if all_orders:
            date_fields = ["date", "created_at", "order_date", "dateCreated", "data"]
            order_dates = []
            for order in all_orders:
                for field in date_fields:
                    val = order.get(field)
                    if val:
                        order_dates.append(str(val)[:10])
                        break
            if order_dates:
                order_dates.sort()
                logger.info(f"easySales: actual order date range = {order_dates[0]} → {order_dates[-1]} (requested: {start_date} → {end_date})")

        return all_orders
    
    def calculate_daily_sales(
        self,
        orders: List[Dict],
        days_in_period: int
    ) -> Dict[str, Dict]:
        """
        Calculate daily sales velocity per SKU from orders.

        Args:
            orders: List of orders from API
            days_in_period: Number of days in the analysis period

        Returns:
            Dictionary mapping SKU to sales metrics
        """
        sales_by_sku = {}

        for order in orders:
            order_id = order.get("id")
            items = order.get("items") or order.get("products") or []

            for item in items:
                sku = item.get("sku") or item.get("code") or item.get("product_code")
                quantity = float(item.get("quantity", 0))

                if sku and quantity > 0:
                    if sku not in sales_by_sku:
                        sales_by_sku[sku] = {
                            "sku": sku,
                            "name": item.get("name") or item.get("product_name", ""),
                            "total_quantity": 0,
                            "order_ids": set(),
                        }

                    sales_by_sku[sku]["total_quantity"] += quantity
                    if order_id is not None:
                        sales_by_sku[sku]["order_ids"].add(order_id)

        for sku, data in sales_by_sku.items():
            data["days_in_period"] = days_in_period
            data["order_count"] = len(data.pop("order_ids"))
            if days_in_period > 0:
                data["daily_sales"] = data["total_quantity"] / days_in_period
            else:
                data["daily_sales"] = 0

        return sales_by_sku
    
    def get_sales_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_back: int = 30,
        max_pages: int = 10
    ) -> Dict[str, Dict]:
        """
        Get processed sales data with daily velocity calculations.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            days_back: Number of days in the period (used for daily sales calculation)
            max_pages: Maximum number of pages to fetch from the API

        Returns:
            Dictionary mapping SKU to sales metrics
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if not start_date:
            start = datetime.now() - timedelta(days=days_back)
            start_date = start.strftime("%Y-%m-%d")

        orders = self.get_orders(start_date, end_date, days_back, max_pages)

        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            # "after" is exclusive in the API, so actual range is end - start (not +1)
            actual_days = max((end_dt - start_dt).days, 1)
        else:
            actual_days = days_back

        return self.calculate_daily_sales(orders, actual_days)


def get_easysales_client() -> Optional[EasySalesAPI]:
    """
    Create easySales API client from environment variables.
    
    Returns:
        EasySalesAPI instance or None if token not found
    """
    token = os.getenv("EASYSALES_TOKEN")
    
    if not token:
        return None
    
    return EasySalesAPI(token)
