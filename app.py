import logging
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

from smartbill_api import get_smartbill_client
from easysales_api import get_easysales_client
from sheets_api import get_sheets_client
from forecast import InventoryForecast
from alerts import get_alert_system

load_dotenv()

@st.cache_resource
def get_database_functions():
    """Lazy database initialization - only connects when first accessed"""
    if not all([os.getenv("PGHOST"), os.getenv("PGDATABASE"), os.getenv("PGUSER")]):
        return None, None, None, None, None, False
    
    try:
        from database import (
            init_database, save_forecast_run, save_forecast_details,
            get_forecast_history, get_forecast_details, get_sku_history
        )
        init_database()
        return save_forecast_run, save_forecast_details, get_forecast_history, get_forecast_details, get_sku_history, True
    except Exception as e:
        logging.error(f"Database not available: {e}")
        return None, None, None, None, None, False

st.set_page_config(
    page_title="Inventory Forecast System",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Inventory Forecast System")
st.markdown("Calculate purchasing requirements based on sales velocity and current stock levels")

st.sidebar.header("Configuration")

st.sidebar.markdown("**Stock Source:** SmartBill (gestiune StocCV)")

data_source = st.sidebar.radio(
    "Sales Data Source",
    ["easySales", "SmartBill"],
    help="Select the source for sales/orders data. Stock is always from SmartBill."
)

st.sidebar.subheader("Date Range")

use_custom_dates = st.sidebar.checkbox("Use Custom Date Range", value=False)

if use_custom_dates:
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now() - timedelta(days=60),
            max_value=datetime.now()
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime.now(),
            max_value=datetime.now()
        )
    
    if start_date > end_date:
        st.sidebar.error("Start date must be before or equal to end date")
        st.stop()
    
    days_interval = max((end_date - start_date).days + 1, 1)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
else:
    days_interval = st.sidebar.selectbox(
        "Analysis Period (days)",
        [30, 60, 90],
        index=1,
        help="Number of days to analyze for calculating daily sales velocity"
    )
    end_date_str = datetime.now().strftime("%Y-%m-%d")
    start_date_str = (datetime.now() - timedelta(days=days_interval - 1)).strftime("%Y-%m-%d")

forecast_months = st.sidebar.multiselect(
    "Forecast Horizons (months)",
    [3, 4, 5, 6, 9],
    default=[3, 4, 5, 6, 9],
    help="Time horizons for inventory requirements"
)

warehouse_name = st.sidebar.text_input(
    "SmartBill Warehouse (gestiune)",
    value="StocCV",
    help="Warehouse name for stock data from SmartBill. Default: StocCV"
)

min_daily_sales = st.sidebar.number_input(
    "Minimum Daily Sales Filter",
    min_value=0.0,
    value=0.01,
    step=0.01,
    help="Only show products with daily sales above this threshold"
)

st.sidebar.markdown("---")
st.sidebar.header("Safety Stock Settings")

safety_stock_percentage = st.sidebar.slider(
    "Safety Stock Buffer (%)",
    min_value=0,
    max_value=100,
    value=InventoryForecast.DEFAULT_SAFETY_STOCK_PERCENTAGE,
    step=5,
    help="Additional buffer percentage to add to forecast requirements"
)

st.sidebar.markdown("---")
st.sidebar.header("Google Sheets Settings")

use_sheets = st.sidebar.checkbox("Load Incoming from Google Sheets", value=True)

if use_sheets:
    sheet_id = st.sidebar.text_input(
        "Sheet ID",
        value=os.getenv("GOOGLE_SHEET_ID", ""),
        help="Google Sheets spreadsheet ID (from URL)"
    )
    worksheet_name = st.sidebar.text_input(
        "Worksheet Name",
        value=os.getenv("GOOGLE_WORKSHEET_NAME", "Sheet1")
    )
    sku_column = st.sidebar.text_input("SKU Column Name", value="SKU")
    incoming_column = st.sidebar.text_input("Incoming Column Name", value="Incoming")
else:
    sheet_id = worksheet_name = sku_column = incoming_column = None

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Run Forecast", type="primary", use_container_width=True):
    with st.spinner("Fetching data and calculating forecast..."):
        errors = []
        warnings = []
        
        cif = os.getenv("SMARTBILL_CIF")
        if not cif:
            errors.append("SMARTBILL_CIF not configured in environment variables")
        
        smartbill_client = get_smartbill_client()
        if not smartbill_client:
            warnings.append("SmartBill credentials not configured - stock data unavailable")
        
        easysales_client = get_easysales_client()
        if not easysales_client:
            warnings.append("easySales credentials not configured - sales data unavailable")
        
        sheets_client = None
        if use_sheets:
            sheets_client = get_sheets_client()
            if not sheets_client:
                warnings.append("Google Sheets credentials not configured - incoming data unavailable")
        
        if errors:
            st.error("Configuration errors:")
            for error in errors:
                st.error(f"❌ {error}")
            st.stop()
        
        if warnings:
            st.warning("Configuration warnings:")
            for warning in warnings:
                st.warning(f"⚠️ {warning}")
        
        stock_data = {}
        if smartbill_client and cif:
            with st.spinner("Fetching stock data from SmartBill..."):
                stock_list = smartbill_client.get_stock(cif, warehouse_name=warehouse_name)
                stock_data = smartbill_client.parse_stock_data(stock_list)
                st.success(f"✓ Loaded {len(stock_data)} products from SmartBill stock")
        
        sales_data = {}
        if data_source == "easySales":
            if easysales_client:
                with st.spinner(f"Fetching sales data from easySales ({start_date_str} to {end_date_str})..."):
                    sales_data = easysales_client.get_sales_data(
                        start_date=start_date_str,
                        end_date=end_date_str,
                        days_back=days_interval
                    )
                    st.success(f"✓ Analyzed {len(sales_data)} products from easySales orders")
            else:
                st.error("easySales credentials not configured. Cannot fetch sales data.")
        elif data_source == "SmartBill":
            if smartbill_client and cif:
                with st.spinner(f"Fetching sales data from SmartBill invoices ({start_date_str} to {end_date_str})..."):
                    sales_data = smartbill_client.get_sales_data(
                        cif=cif,
                        start_date=start_date_str,
                        end_date=end_date_str,
                        days_back=days_interval
                    )
                    st.success(f"✓ Analyzed {len(sales_data)} products from SmartBill invoices")
            else:
                st.error("SmartBill credentials not configured. Cannot fetch sales data.")
        
        incoming_data = {}
        if use_sheets and sheets_client and sheet_id:
            with st.spinner("Fetching incoming data from Google Sheets..."):
                incoming_data = sheets_client.get_incoming_quantities(
                    sheet_id=sheet_id,
                    worksheet_name=worksheet_name,
                    sku_column=sku_column,
                    incoming_column=incoming_column
                )
                st.success(f"✓ Loaded incoming data for {len(incoming_data)} SKUs from Google Sheets")
        
        if not stock_data and not sales_data:
            st.error("No data available. Please configure at least one data source (SmartBill or easySales).")
            st.stop()
        
        with st.spinner("Calculating forecast requirements..."):
            df_forecast = InventoryForecast.calculate_requirements(
                stock_data=stock_data,
                sales_data=sales_data,
                incoming_data=incoming_data,
                forecast_months=forecast_months,
                safety_stock_percentage=safety_stock_percentage
            )
        
        df_filtered = InventoryForecast.filter_active_products(df_forecast, min_daily_sales)
        
        db_save_run, db_save_details, _, _, _, db_ok = get_database_functions()
        if db_ok:
            with st.spinner("Saving forecast to database..."):
                try:
                    if db_save_run and db_save_details:
                        run_id = db_save_run(
                            data_source=data_source,
                            start_date=start_date_str,
                            end_date=end_date_str,
                            days_analyzed=days_interval,
                            warehouse_name=warehouse_name or None,
                            total_products=len(df_forecast),
                            notes=f"Safety stock: {safety_stock_percentage}%"
                        )
                        
                        forecast_records = df_forecast.to_dict('records')
                        db_save_details(run_id, forecast_records)
                        
                        st.success(f"✓ Forecast saved to database (Run ID: {run_id})")
                        st.session_state['last_run_id'] = run_id
                except Exception as e:
                    st.warning(f"Could not save to database: {e}")
        
        st.session_state['forecast_data'] = df_filtered
        st.session_state['full_forecast_data'] = df_forecast
        st.session_state['last_update'] = datetime.now()
        st.session_state['current_config'] = {
            'data_source': data_source,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'days_interval': days_interval,
            'safety_stock': safety_stock_percentage
        }

if 'forecast_data' in st.session_state:
    df = st.session_state['forecast_data']
    
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Products", len(df))
    with col2:
        st.metric("Total Current Stock", f"{df['Current Stock'].sum():,.0f}")
    with col3:
        st.metric("Total Incoming", f"{df['Incoming'].sum():,.0f}")
    with col4:
        if forecast_months and f"Required {min(forecast_months)}M" in df.columns:
            total_req = df[f"Required {min(forecast_months)}M"].sum()
            st.metric(f"Total Required ({min(forecast_months)}M)", f"{total_req:,.0f}")
    
    st.markdown("---")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Full Forecast", "🔴 Critical Items", "📈 Statistics", "📜 History & Trends"])
    
    with tab1:
        st.subheader("Complete Forecast Results")
        
        if 'last_update' in st.session_state:
            st.caption(f"Last updated: {st.session_state['last_update'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        st.dataframe(
            df,
            use_container_width=True,
            height=500
        )
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download as CSV",
            data=csv,
            file_name=f"inventory_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    with tab2:
        st.subheader("Critical Items - Immediate Ordering Required")
        
        critical_horizon = st.selectbox(
            "Time Horizon",
            forecast_months,
            index=0 if forecast_months else None
        )
        
        if critical_horizon:
            df_critical = InventoryForecast.get_critical_items(df, critical_horizon)
            
            if not df_critical.empty:
                st.warning(f"⚠️ {len(df_critical)} items need ordering for {critical_horizon}-month coverage")
                
                st.dataframe(
                    df_critical,
                    use_container_width=True,
                    height=400
                )
                
                csv_critical = df_critical.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Critical Items",
                    data=csv_critical,
                    file_name=f"critical_items_{critical_horizon}m_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
                
                st.markdown("---")
                st.markdown("#### 📧 Email Alert")
                
                alert_system = get_alert_system()
                if alert_system:
                    email_recipients = st.text_input(
                        "Email Recipients (comma-separated)",
                        help="Enter email addresses to send low stock alerts"
                    )
                    
                    if st.button("Send Alert Email") and email_recipients:
                        recipients = [email.strip() for email in email_recipients.split(',')]
                        success = alert_system.send_low_stock_alert(
                            to_emails=recipients,
                            critical_items=df_critical,
                            forecast_horizon_months=critical_horizon
                        )
                        
                        if success:
                            st.success(f"✓ Alert sent to {len(recipients)} recipient(s)")
                        else:
                            st.error("Failed to send alert. Check SMTP configuration.")
                else:
                    st.info("Email alerts not configured. Set SMTP_SERVER, SMTP_PORT, SMTP_USER, and SMTP_PASSWORD in environment variables.")
            else:
                st.success(f"✓ All items have sufficient stock for {critical_horizon} months")
    
    with tab3:
        st.subheader("Sales Statistics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Top 10 Products by Daily Sales**")
            top_sellers = df.nlargest(10, 'Daily Sales')[['SKU', 'Product Name', 'Daily Sales']]
            st.dataframe(top_sellers, use_container_width=True)
        
        with col2:
            st.markdown("**Products with Zero Sales**")
            zero_sales = df[df['Daily Sales'] == 0][['SKU', 'Product Name', 'Current Stock']]
            st.dataframe(zero_sales.head(10), use_container_width=True)
            if len(zero_sales) > 10:
                st.caption(f"Showing 10 of {len(zero_sales)} products with no sales")
        
        st.markdown("---")
        
        st.markdown("**Daily Sales Distribution**")
        st.bar_chart(df.set_index('SKU')['Daily Sales'].head(20))
    
    with tab4:
        st.subheader("Historical Trends & Forecast Accuracy")
        
        _, _, db_get_history, _, db_get_sku_history, db_ok = get_database_functions()
        if not db_ok:
            st.info("📊 Historical tracking requires database configuration. Set up PostgreSQL credentials to enable this feature.")
            st.markdown("""
            **Required Environment Variables:**
            - `PGHOST` - PostgreSQL host
            - `PGDATABASE` - Database name
            - `PGUSER` - Database user
            - `PGPASSWORD` - Database password
            - `PGPORT` - Database port
            """)
        else:
            try:
                history = db_get_history(limit=20) if db_get_history else []
            
                if history:
                    st.markdown("#### Recent Forecast Runs")
                    
                    history_df = pd.DataFrame(history)
                    history_df['run_date'] = pd.to_datetime(history_df['run_date']).dt.strftime('%Y-%m-%d %H:%M')
                    
                    st.dataframe(
                        history_df[['id', 'run_date', 'data_source', 'start_date', 'end_date', 'days_analyzed', 'warehouse_name', 'total_products']],
                        use_container_width=True,
                        height=300
                    )
                    
                    st.markdown("---")
                    st.markdown("#### SKU Historical Analysis")
                    
                    sku_to_analyze = st.selectbox(
                        "Select SKU to view history",
                        options=df['SKU'].tolist() if not df.empty else [],
                        help="View historical forecast data for a specific SKU"
                    )
                    
                    if sku_to_analyze and db_get_sku_history:
                        sku_history = db_get_sku_history(sku_to_analyze, limit=15)
                        
                        if sku_history:
                            sku_df = pd.DataFrame(sku_history)
                            sku_df['run_date'] = pd.to_datetime(sku_df['run_date']).dt.strftime('%Y-%m-%d')
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**Stock & Sales Trends**")
                                chart_data = sku_df[['run_date', 'current_stock', 'daily_sales']].set_index('run_date')
                                st.line_chart(chart_data)
                            
                            with col2:
                                st.markdown("**Requirement Trends (3M)**")
                                req_chart = sku_df[['run_date', 'required_3m']].set_index('run_date')
                                st.line_chart(req_chart)
                            
                            st.markdown("**Historical Data**")
                            st.dataframe(sku_df, use_container_width=True)
                        else:
                            st.info(f"No historical data found for SKU: {sku_to_analyze}")
                else:
                    st.info("No forecast history available yet. Run a forecast to start tracking data.")
            
            except Exception as e:
                st.error(f"Error loading historical data: {e}")

else:
    st.info("👈 Configure settings in the sidebar and click 'Run Forecast' to begin")
    
    st.markdown("### 📋 Setup Instructions")
    
    st.markdown("""
    #### Required Configuration
    
    1. **Environment Variables** - Set up in `.env` file or Replit Secrets:
       - `SMARTBILL_EMAIL` - Your SmartBill account email
       - `SMARTBILL_TOKEN` - SmartBill API token
       - `SMARTBILL_CIF` - Company fiscal identification code
       - `EASYSALES_TOKEN` - easySales API Bearer token
       - `GOOGLE_CREDENTIALS_JSON` or `GOOGLE_CREDENTIALS_PATH` - Google service account credentials
       - `GOOGLE_SHEET_ID` - (Optional) Default Google Sheet ID
       - `GOOGLE_WORKSHEET_NAME` - (Optional) Default worksheet name
    
    2. **Google Sheets Format** - Your sheet should have columns:
       - `SKU` - Product SKU/code
       - `Incoming` - Quantity of incoming inventory
    
    3. **Forecast Formula**:
       ```
       Required = (Daily Sales × Days Needed × Safety Multiplier) - Current Stock - Incoming
       ```
       
       Where:
       - Daily Sales = Total Sold / Analysis Period Days
       - Days Needed = Forecast Months × 30
       - Safety Multiplier = 1 + (Safety Stock % / 100)
       - Negative result = You have enough stock (surplus)
    """)
