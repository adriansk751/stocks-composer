import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os


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
        days_back: int = 30
    ) -> List[Dict]:
        """
        Retrieve orders from easySales API.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            days_back: Number of days to look back if dates not provided
        
        Returns:
            List of orders
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        if not start_date:
            start = datetime.now() - timedelta(days=days_back)
            start_date = start.strftime("%Y-%m-%d")
        
        all_orders = []
        page = 1

        while True:
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
                    all_orders.extend(data)
                    break
                elif isinstance(data, dict) and "data" in data:
                    page_orders = data["data"]
                    all_orders.extend(page_orders)

                    meta = data.get("meta", {})
                    per_page = meta.get("per_page", len(page_orders))

                    print(f"easySales: fetched page {page} ({len(page_orders)} orders)")

                    if len(page_orders) < per_page:
                        break
                    page += 1
                else:
                    break

            except requests.exceptions.RequestException as e:
                print(f"Error fetching orders from easySales (page {page}): {e}")
                break

        print(f"easySales: total orders fetched = {len(all_orders)}")
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
                            "order_count": 0
                        }
                    
                    sales_by_sku[sku]["total_quantity"] += quantity
                    sales_by_sku[sku]["order_count"] += 1
        
        for sku, data in sales_by_sku.items():
            if days_in_period > 0:
                data["daily_sales"] = data["total_quantity"] / days_in_period
            else:
                data["daily_sales"] = 0
        
        return sales_by_sku
    
    def get_sales_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_back: int = 30
    ) -> Dict[str, Dict]:
        """
        Get processed sales data with daily velocity calculations.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format  
            days_back: Number of days in the period (used for daily sales calculation)
        
        Returns:
            Dictionary mapping SKU to sales metrics
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        if not start_date:
            start = datetime.now() - timedelta(days=days_back - 1)
            start_date = start.strftime("%Y-%m-%d")
        
        orders = self.get_orders(start_date, end_date, days_back)
        
        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            actual_days = max((end_dt - start_dt).days + 1, 1)
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
