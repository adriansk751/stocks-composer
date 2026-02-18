import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
from typing import Dict, List, Optional
import json


def get_db_connection():
    """Create a database connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD")
    )


def init_database():
    """Initialize database tables for forecast history tracking."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forecast_runs (
            id SERIAL PRIMARY KEY,
            run_date TIMESTAMP NOT NULL DEFAULT NOW(),
            data_source VARCHAR(50) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            days_analyzed INTEGER NOT NULL,
            warehouse_name VARCHAR(255),
            total_products INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forecast_details (
            id SERIAL PRIMARY KEY,
            run_id INTEGER REFERENCES forecast_runs(id) ON DELETE CASCADE,
            sku VARCHAR(255) NOT NULL,
            product_name VARCHAR(500),
            unit VARCHAR(50),
            current_stock DECIMAL(12, 4),
            incoming_qty DECIMAL(12, 4),
            daily_sales DECIMAL(12, 6),
            required_3m DECIMAL(12, 4),
            required_4m DECIMAL(12, 4),
            required_5m DECIMAL(12, 4),
            required_6m DECIMAL(12, 4),
            required_9m DECIMAL(12, 4),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_forecast_runs_date 
        ON forecast_runs(run_date DESC)
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_forecast_details_sku 
        ON forecast_details(sku)
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_forecast_details_run 
        ON forecast_details(run_id)
    """)
    
    conn.commit()
    cur.close()
    conn.close()


def save_forecast_run(
    data_source: str,
    start_date: str,
    end_date: str,
    days_analyzed: int,
    warehouse_name: Optional[str],
    total_products: int,
    notes: Optional[str] = None
) -> int:
    """
    Save a forecast run to the database.
    
    Returns:
        The ID of the created forecast run
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO forecast_runs 
        (data_source, start_date, end_date, days_analyzed, warehouse_name, total_products, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (data_source, start_date, end_date, days_analyzed, warehouse_name, total_products, notes))
    
    run_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    return run_id


def save_forecast_details(run_id: int, forecast_data: List[Dict]):
    """
    Save forecast details for a specific run.
    
    Args:
        run_id: ID of the forecast run
        forecast_data: List of dictionaries containing forecast data
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    for row in forecast_data:
        cur.execute("""
            INSERT INTO forecast_details 
            (run_id, sku, product_name, unit, current_stock, incoming_qty, daily_sales,
             required_3m, required_4m, required_5m, required_6m, required_9m)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            run_id,
            row.get('SKU'),
            row.get('Product Name'),
            row.get('Unit'),
            row.get('Current Stock'),
            row.get('Incoming'),
            row.get('Daily Sales'),
            row.get('Required 3M'),
            row.get('Required 4M'),
            row.get('Required 5M'),
            row.get('Required 6M'),
            row.get('Required 9M')
        ))
    
    conn.commit()
    cur.close()
    conn.close()


def get_forecast_history(limit: int = 50) -> List[Dict]:
    """
    Retrieve forecast run history.
    
    Args:
        limit: Maximum number of runs to retrieve
    
    Returns:
        List of forecast runs
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            id,
            run_date,
            data_source,
            start_date,
            end_date,
            days_analyzed,
            warehouse_name,
            total_products,
            notes
        FROM forecast_runs
        ORDER BY run_date DESC
        LIMIT %s
    """, (limit,))
    
    runs = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(row) for row in runs]


def get_forecast_details(run_id: int) -> List[Dict]:
    """
    Retrieve forecast details for a specific run.
    
    Args:
        run_id: ID of the forecast run
    
    Returns:
        List of forecast detail records
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            sku,
            product_name,
            unit,
            current_stock,
            incoming_qty,
            daily_sales,
            required_3m,
            required_4m,
            required_5m,
            required_6m,
            required_9m
        FROM forecast_details
        WHERE run_id = %s
        ORDER BY daily_sales DESC
    """, (run_id,))
    
    details = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(row) for row in details]


def get_sku_history(sku: str, limit: int = 10) -> List[Dict]:
    """
    Get historical forecast data for a specific SKU.
    
    Args:
        sku: Product SKU
        limit: Maximum number of records
    
    Returns:
        List of historical forecast data for the SKU
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            fr.run_date,
            fr.data_source,
            fd.current_stock,
            fd.incoming_qty,
            fd.daily_sales,
            fd.required_3m
        FROM forecast_details fd
        JOIN forecast_runs fr ON fd.run_id = fr.id
        WHERE fd.sku = %s
        ORDER BY fr.run_date DESC
        LIMIT %s
    """, (sku, limit))
    
    history = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(row) for row in history]


def delete_old_forecasts(days_to_keep: int = 90):
    """
    Delete forecast runs older than specified days.
    
    Args:
        days_to_keep: Number of days of history to retain
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM forecast_runs
        WHERE run_date < NOW() - INTERVAL '%s days'
    """, (days_to_keep,))
    
    deleted = cur.rowcount
    
    conn.commit()
    cur.close()
    conn.close()
    
    return deleted
