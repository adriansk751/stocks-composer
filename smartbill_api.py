import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os


class SmartBillAPI:
    BASE_URL = "https://ws.smartbill.ro/SBORO/api"
    
    def __init__(self, email: str, token: str):
        self.email = email
        self.token = token
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.auth = (email, token)
    
    def get_stock(
        self, 
        cif: str, 
        date: Optional[str] = None, 
        warehouse_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve stock information from SmartBill.
        
        Args:
            cif: Company fiscal identification code
            date: Date in YYYY-MM-DD format (defaults to today)
            warehouse_name: Name of the warehouse (optional)
        
        Returns:
            List of products with stock information
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        params = {
            "cif": cif,
            "date": date
        }
        
        if warehouse_name:
            params["warehouseName"] = warehouse_name
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/stocks",
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if isinstance(data, dict) and "stocks" in data:
                return data["stocks"]
            elif isinstance(data, list):
                return data
            else:
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching stock from SmartBill: {e}")
            return []
    
    def parse_stock_data(self, stock_data: List[Dict]) -> Dict[str, Dict]:
        """
        Parse stock data into a dictionary keyed by product code (SKU).
        
        Args:
            stock_data: Raw stock data from API
        
        Returns:
            Dictionary mapping SKU to stock information
        """
        parsed = {}
        
        for item in stock_data:
            sku = item.get("productCode") or item.get("code") or item.get("sku")
            if sku:
                parsed[sku] = {
                    "sku": sku,
                    "name": item.get("productName") or item.get("name", ""),
                    "quantity": float(item.get("quantity", 0)),
                    "unit": item.get("measuringUnit") or item.get("unit", "buc")
                }
        
        return parsed
    
    def get_invoices(
        self,
        cif: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve invoices from SmartBill for sales analysis.
        
        Args:
            cif: Company fiscal identification code
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        
        Returns:
            List of invoices
        """
        params = {
            "cif": cif,
            "startDate": start_date or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "endDate": end_date or datetime.now().strftime("%Y-%m-%d")
        }
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/invoice/list",
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if isinstance(data, dict) and "list" in data:
                return data["list"]
            elif isinstance(data, list):
                return data
            else:
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching invoices from SmartBill: {e}")
            return []
    
    def calculate_daily_sales_from_invoices(
        self,
        invoices: List[Dict],
        days_in_period: int
    ) -> Dict[str, Dict]:
        """
        Calculate daily sales velocity from SmartBill invoices.
        
        Args:
            invoices: List of invoices from API
            days_in_period: Number of days in the analysis period
        
        Returns:
            Dictionary mapping SKU to sales metrics
        """
        sales_by_sku = {}
        
        for invoice in invoices:
            products = invoice.get("products") or invoice.get("items") or []
            
            for product in products:
                sku = product.get("code") or product.get("productCode") or product.get("sku")
                quantity = float(product.get("quantity", 0))
                
                if sku and quantity > 0:
                    if sku not in sales_by_sku:
                        sales_by_sku[sku] = {
                            "sku": sku,
                            "name": product.get("name") or product.get("productName", ""),
                            "total_quantity": 0,
                            "invoice_count": 0
                        }
                    
                    sales_by_sku[sku]["total_quantity"] += quantity
                    sales_by_sku[sku]["invoice_count"] += 1
        
        for sku, data in sales_by_sku.items():
            if days_in_period > 0:
                data["daily_sales"] = data["total_quantity"] / days_in_period
            else:
                data["daily_sales"] = 0
        
        return sales_by_sku
    
    def get_sales_data(
        self,
        cif: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_back: int = 30
    ) -> Dict[str, Dict]:
        """
        Get processed sales data from SmartBill invoices.
        
        Args:
            cif: Company fiscal identification code
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            days_back: Number of days to look back if dates not provided
        
        Returns:
            Dictionary mapping SKU to sales metrics
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        if not start_date:
            start = datetime.now() - timedelta(days=days_back)
            start_date = start.strftime("%Y-%m-%d")
        
        invoices = self.get_invoices(cif, start_date, end_date)
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        actual_days = (end_dt - start_dt).days + 1
        
        return self.calculate_daily_sales_from_invoices(invoices, actual_days)


def get_smartbill_client() -> Optional[SmartBillAPI]:
    """
    Create SmartBill API client from environment variables.
    
    Returns:
        SmartBillAPI instance or None if credentials not found
    """
    email = os.getenv("SMARTBILL_EMAIL")
    token = os.getenv("SMARTBILL_TOKEN")
    
    if not email or not token:
        return None
    
    return SmartBillAPI(email, token)
