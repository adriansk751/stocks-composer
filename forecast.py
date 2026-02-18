from typing import Dict, List
import pandas as pd


class InventoryForecast:
    MONTHS_TO_DAYS = {
        3: 90,
        4: 120,
        5: 150,
        6: 180,
        9: 270
    }
    
    DEFAULT_SAFETY_STOCK_PERCENTAGE = 20
    
    @staticmethod
    def calculate_requirements(
        stock_data: Dict[str, Dict],
        sales_data: Dict[str, Dict],
        incoming_data: Dict[str, float],
        forecast_months: List[int] = [3, 4, 5, 6, 9],
        safety_stock_percentage: float = 0
    ) -> pd.DataFrame:
        """
        Calculate inventory requirements for each SKU across multiple time horizons.
        
        Formula: Required = (Daily Sales × Days Needed × (1 + Safety%)) - Current Stock - Incoming
        
        Args:
            stock_data: Dictionary mapping SKU to stock information
            sales_data: Dictionary mapping SKU to sales metrics
            incoming_data: Dictionary mapping SKU to incoming quantities
            forecast_months: List of months to forecast (default: [3, 4, 5, 6, 9])
            safety_stock_percentage: Additional buffer percentage (0-100)
        
        Returns:
            DataFrame with forecast results
        """
        all_skus = set(stock_data.keys()) | set(sales_data.keys()) | set(incoming_data.keys())
        
        results = []
        
        for sku in all_skus:
            stock_info = stock_data.get(sku, {})
            sales_info = sales_data.get(sku, {})
            
            current_stock = stock_info.get("quantity", 0)
            incoming = incoming_data.get(sku, 0)
            daily_sales = sales_info.get("daily_sales", 0)
            
            product_name = stock_info.get("name") or sales_info.get("name", "Unknown")
            unit = stock_info.get("unit", "buc")
            
            safety_multiplier = 1 + (safety_stock_percentage / 100)
            
            row = {
                "SKU": sku,
                "Product Name": product_name,
                "Unit": unit,
                "Current Stock": round(current_stock, 2),
                "Incoming": round(incoming, 2),
                "Daily Sales": round(daily_sales, 4),
                "Safety Stock %": safety_stock_percentage,
            }
            
            for months in forecast_months:
                days = InventoryForecast.MONTHS_TO_DAYS.get(months, months * 30)
                
                demand = daily_sales * days * safety_multiplier
                required = demand - current_stock - incoming
                
                row[f"Required {months}M"] = round(required, 2)
            
            results.append(row)
        
        df = pd.DataFrame(results)
        
        df = df.sort_values("Daily Sales", ascending=False)
        
        return df
    
    @staticmethod
    def filter_active_products(df: pd.DataFrame, min_daily_sales: float = 0.01) -> pd.DataFrame:
        """
        Filter dataframe to show only products with meaningful sales activity.
        
        Args:
            df: Forecast dataframe
            min_daily_sales: Minimum daily sales threshold
        
        Returns:
            Filtered dataframe
        """
        return df[df["Daily Sales"] >= min_daily_sales].copy()
    
    @staticmethod
    def get_critical_items(df: pd.DataFrame, horizon_months: int = 3) -> pd.DataFrame:
        """
        Identify items that need immediate ordering based on forecast.
        
        Args:
            df: Forecast dataframe
            horizon_months: Time horizon to check (default: 3 months)
        
        Returns:
            Dataframe with items that have positive requirements
        """
        column_name = f"Required {horizon_months}M"
        
        if column_name not in df.columns:
            return pd.DataFrame()
        
        critical = df[df[column_name] > 0].copy()
        critical = critical.sort_values(column_name, ascending=False)
        
        return critical
