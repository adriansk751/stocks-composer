import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from smartbill_api import get_smartbill_client
from easysales_api import get_easysales_client
from sheets_api import get_sheets_client
from forecast import InventoryForecast

load_dotenv()

st.set_page_config(
    page_title="Multi-Warehouse Comparison",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 Multi-Warehouse Comparison")
st.markdown("Compare inventory and forecast requirements across multiple warehouses")

st.sidebar.header("Configuration")

data_source = st.sidebar.radio(
    "Sales Data Source",
    ["easySales", "SmartBill"],
    help="Select the source for sales data"
)

if data_source == "easySales":
    easysales_max_pages = st.sidebar.number_input(
        "easySales Max Pages",
        min_value=1,
        max_value=100,
        value=10,
        step=1,
        help="Maximum number of order pages to fetch from easySales"
    )
    easysales_status = st.sidebar.text_input(
        "Order Status Filter",
        value="",
        help="Only count orders with this status (e.g. finalizata). Leave empty to include all."
    ).strip() or None
else:
    easysales_max_pages = 10
    easysales_status = None

days_interval = st.sidebar.selectbox(
    "Analysis Period (days)",
    [30, 60, 90],
    index=1
)

forecast_horizon = st.sidebar.selectbox(
    "Forecast Horizon (months)",
    [3, 4, 5, 6, 9],
    index=0
)

safety_stock_percentage = st.sidebar.slider(
    "Safety Stock Buffer (%)",
    min_value=0,
    max_value=100,
    value=InventoryForecast.DEFAULT_SAFETY_STOCK_PERCENTAGE,
    step=5
)

st.sidebar.markdown("---")

warehouse_list_input = st.sidebar.text_area(
    "Warehouse Names (one per line)",
    value="Main Warehouse\nSecondary Warehouse",
    help="Enter warehouse names to compare, one per line"
)

warehouses = [w.strip() for w in warehouse_list_input.split('\n') if w.strip()]

use_sheets = st.sidebar.checkbox("Load Incoming from Google Sheets", value=False)

if use_sheets:
    sheet_id = st.sidebar.text_input(
        "Sheet ID",
        value=os.getenv("GOOGLE_SHEET_ID", "")
    )
    worksheet_name = st.sidebar.text_input("Worksheet Name", value="Sheet1")
else:
    sheet_id = worksheet_name = None

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Compare Warehouses", type="primary", use_container_width=True):
    if not warehouses:
        st.error("Please enter at least one warehouse name")
        st.stop()
    
    with st.spinner("Fetching and comparing warehouse data..."):
        cif = os.getenv("SMARTBILL_CIF")
        if not cif:
            st.error("SMARTBILL_CIF not configured")
            st.stop()
        
        smartbill_client = get_smartbill_client()
        easysales_client = get_easysales_client()
        sheets_client = get_sheets_client() if use_sheets else None
        
        if not smartbill_client:
            st.error("SmartBill credentials not configured")
            st.stop()
        
        end_date_str = datetime.now().strftime("%Y-%m-%d")
        start_date_str = (datetime.now() - timedelta(days=days_interval - 1)).strftime("%Y-%m-%d")
        
        warehouse_data = {}
        
        for warehouse in warehouses:
            with st.spinner(f"Processing {warehouse}..."):
                stock_list = smartbill_client.get_stock(cif, warehouse_name=warehouse)
                stock_data = smartbill_client.parse_stock_data(stock_list)
                
                sales_data = {}
                if data_source == "easySales" and easysales_client:
                    sales_data = easysales_client.get_sales_data(
                        start_date=start_date_str,
                        end_date=end_date_str,
                        days_back=days_interval,
                        max_pages=easysales_max_pages,
                        order_status=easysales_status
                    )
                elif data_source == "SmartBill" and smartbill_client:
                    sales_data = smartbill_client.get_sales_data(
                        cif=cif,
                        start_date=start_date_str,
                        end_date=end_date_str,
                        days_back=days_interval
                    )
                
                incoming_data = {}
                if use_sheets and sheets_client and sheet_id:
                    incoming_data = sheets_client.get_incoming_quantities(
                        sheet_id=sheet_id,
                        worksheet_name=worksheet_name
                    )
                
                df_forecast = InventoryForecast.calculate_requirements(
                    stock_data=stock_data,
                    sales_data=sales_data,
                    incoming_data=incoming_data,
                    forecast_months=[forecast_horizon],
                    safety_stock_percentage=safety_stock_percentage
                )
                
                warehouse_data[warehouse] = {
                    'forecast': df_forecast,
                    'total_stock': df_forecast['Current Stock'].sum(),
                    'total_incoming': df_forecast['Incoming'].sum(),
                    'total_required': df_forecast[f'Required {forecast_horizon}M'].sum(),
                    'critical_items': len(df_forecast[df_forecast[f'Required {forecast_horizon}M'] > 0])
                }
        
        st.session_state['warehouse_comparison'] = warehouse_data
        st.session_state['comparison_config'] = {
            'warehouses': warehouses,
            'horizon': forecast_horizon,
            'safety_stock': safety_stock_percentage
        }

if 'warehouse_comparison' in st.session_state:
    data = st.session_state['warehouse_comparison']
    config = st.session_state['comparison_config']
    
    st.markdown("---")
    st.subheader("Warehouse Comparison Summary")
    
    cols = st.columns(len(config['warehouses']))
    for idx, warehouse in enumerate(config['warehouses']):
        wh_data = data.get(warehouse, {})
        with cols[idx]:
            st.metric(
                warehouse,
                f"{wh_data.get('total_stock', 0):,.0f}",
                help="Total current stock"
            )
            st.caption(f"Required: {wh_data.get('total_required', 0):,.0f}")
            st.caption(f"Critical: {wh_data.get('critical_items', 0)} items")
    
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["📊 Side-by-Side", "🔗 Consolidated View", "📈 Charts"])
    
    with tab1:
        st.subheader("Side-by-Side Comparison")
        
        for warehouse in config['warehouses']:
            st.markdown(f"### {warehouse}")
            df = data[warehouse]['forecast']
            
            critical = df[df[f"Required {config['horizon']}M"] > 0]
            if not critical.empty:
                st.warning(f"⚠️ {len(critical)} items need ordering")
                st.dataframe(
                    critical[['SKU', 'Product Name', 'Current Stock', 'Daily Sales', f"Required {config['horizon']}M"]],
                    use_container_width=True,
                    height=300
                )
            else:
                st.success("✓ All items have sufficient stock")
            
            st.markdown("---")
    
    with tab2:
        st.subheader("Consolidated Purchasing Recommendations")
        
        all_skus = set()
        for wh_data in data.values():
            all_skus.update(wh_data['forecast']['SKU'].tolist())
        
        consolidated_rows = []
        
        for sku in all_skus:
            row = {'SKU': sku}
            total_stock = 0
            total_shortage = 0
            product_name = ""
            unit = "buc"
            
            for warehouse in config['warehouses']:
                wh_forecast = data[warehouse]['forecast']
                sku_data = wh_forecast[wh_forecast['SKU'] == sku]
                
                if not sku_data.empty:
                    sku_row = sku_data.iloc[0]
                    stock = sku_row['Current Stock']
                    required = sku_row[f"Required {config['horizon']}M"]
                    product_name = sku_row['Product Name']
                    unit = sku_row.get('Unit', 'buc')
                    
                    row[f"{warehouse} Stock"] = stock
                    row[f"{warehouse} Required"] = required
                    total_stock += stock
                    total_shortage += max(required, 0)
                else:
                    row[f"{warehouse} Stock"] = 0
                    row[f"{warehouse} Required"] = 0
            
            row['Product Name'] = product_name
            row['Unit'] = unit
            row['Total Stock'] = total_stock
            row['Total Shortage'] = total_shortage
            row['Consolidated Order'] = total_shortage
            
            consolidated_rows.append(row)
        
        consolidated_df = pd.DataFrame(consolidated_rows)
        consolidated_df = consolidated_df.sort_values('Consolidated Order', ascending=False)
        
        items_to_order = consolidated_df[consolidated_df['Consolidated Order'] > 0]
        
        if not items_to_order.empty:
            st.warning(f"⚠️ {len(items_to_order)} items need consolidated ordering")
            st.dataframe(items_to_order, use_container_width=True, height=500)
            
            csv = items_to_order.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Consolidated Order List",
                data=csv,
                file_name=f"consolidated_order_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.success("✓ All warehouses have sufficient stock")
    
    with tab3:
        st.subheader("Visual Comparison")
        
        chart_data = pd.DataFrame([
            {
                'Warehouse': wh,
                'Total Stock': data[wh]['total_stock'],
                'Total Required': data[wh]['total_required'],
                'Critical Items': data[wh]['critical_items']
            }
            for wh in config['warehouses']
        ])
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Stock vs. Required**")
            st.bar_chart(chart_data.set_index('Warehouse')[['Total Stock', 'Total Required']])
        
        with col2:
            st.markdown("**Critical Items Count**")
            st.bar_chart(chart_data.set_index('Warehouse')['Critical Items'])

else:
    st.info("👈 Configure warehouses in the sidebar and click 'Compare Warehouses' to begin")
    
    st.markdown("""
    ### How to Use
    
    1. **Enter Warehouse Names** - Add warehouse names in the sidebar (one per line)
    2. **Configure Settings** - Select data source, analysis period, and forecast horizon
    3. **Run Comparison** - Click the button to fetch and compare data across all warehouses
    4. **Review Results**:
       - **Side-by-Side**: View each warehouse's critical items separately
       - **Consolidated View**: See combined purchasing recommendations across all warehouses
       - **Charts**: Visual comparison of stock levels and requirements
    """)
