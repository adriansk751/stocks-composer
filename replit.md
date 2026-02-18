# Inventory Forecast System

## Overview

This is an inventory forecasting application built with Streamlit that calculates purchasing requirements based on sales velocity and current stock levels. The system integrates with multiple data sources (SmartBill, easySales, Google Sheets) to provide comprehensive inventory analytics and multi-warehouse comparisons. It calculates daily sales velocity and projects future inventory needs across various time horizons (3, 4, 5, 6, and 9 months) with configurable safety stock buffers.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture

**Framework**: Streamlit
- **Rationale**: Streamlit provides rapid development of data-focused web applications with minimal frontend code. It's ideal for internal business tools and analytics dashboards.
- **Multi-page structure**: The application uses Streamlit's native multi-page architecture with a main app and separate pages (e.g., Multi-Warehouse Comparison).
- **Pros**: Fast development, automatic reactivity, built-in widgets for data inputs
- **Cons**: Limited customization for complex UIs, page reloads on interaction

### Backend Architecture

**Language**: Python
- **Modular design**: Separate modules for each external integration (smartbill_api.py, easysales_api.py, sheets_api.py) plus core logic modules (forecast.py, database.py, alerts.py)
- **Rationale**: Separation of concerns allows independent testing and maintenance of each integration point

**Core Calculation Engine** (forecast.py)
- **InventoryForecast class**: Implements the core business logic for calculating inventory requirements
- **Formula**: `Required = (Daily Sales × Days Needed × (1 + Safety%)) - Current Stock - Incoming`
- **Time horizons**: Supports multiple forecast periods (3, 4, 5, 6, 9 months) mapped to days (90, 120, 150, 180, 270)
- **Rationale**: Centralized calculation logic ensures consistency across all warehouse comparisons and forecast runs

### Data Storage

**Database**: PostgreSQL
- **Connection**: Direct psycopg2 connection using environment variables (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD)
- **Schema**: 
  - `forecast_runs`: Stores metadata for each forecast execution (date range, data source, warehouse)
  - `forecast_details`: Stores individual SKU-level forecast results linked to runs
- **Rationale**: Relational database provides historical tracking, audit trails, and the ability to compare forecasts over time
- **Pros**: ACID compliance, complex querying, historical analysis
- **Cons**: Requires database hosting and management

### Authentication & Authorization

**External API Authentication**:
- **SmartBill**: Basic authentication using email and token
- **easySales**: Bearer token authentication
- **Google Sheets**: Service account credentials (JSON file or JSON string)
- **SMTP**: Username/password for email alerts

**Credential Management**: All credentials stored in environment variables, loaded via dotenv
- **Rationale**: Keeps sensitive data out of code, supports multiple environments (dev/prod)

### Core Business Logic

**Sales Velocity Calculation**:
- Aggregates sales data from chosen source (SmartBill or easySales) over a configurable period (30, 60, or 90 days)
- Calculates daily sales average per SKU
- **Rationale**: Daily sales velocity is the most accurate predictor for variable demand patterns

**Multi-source Data Integration**:
- **Current Stock**: Always from SmartBill API, specifically from warehouse "gestiune StocCV" (default, configurable)
- **Sales History**: User's choice - either easySales OR SmartBill
- **Incoming Inventory**: Retrieved from Google Sheets
- **Rationale**: Combines operational data from multiple systems of record to provide complete inventory picture

**Safety Stock Buffer**:
- Configurable percentage (0-100%) added to base requirements
- **Rationale**: Accounts for demand variability and prevents stockouts

## External Dependencies

### Third-party APIs

1. **SmartBill Cloud API**
   - **Endpoint**: `https://ws.smartbill.ro/SBORO/api`
   - **Purpose**: Retrieve current stock levels and sales data (alternative source)
   - **Authentication**: Basic auth (email + token)
   - **Key endpoints**: 
     - `GET /stocks` - Current inventory by warehouse

2. **easySales API**
   - **Endpoint**: `https://app.easysales.ro/api/v2`
   - **Purpose**: Primary sales data source
   - **Authentication**: Bearer token
   - **Key endpoints**:
     - `GET /orders` - Order history with date filtering

3. **Google Sheets API**
   - **Purpose**: Read incoming/in-transit inventory quantities
   - **Authentication**: Service account credentials (OAuth 2.0)
   - **Library**: gspread with google-auth
   - **Scopes**: spreadsheets.readonly, drive.readonly

4. **SMTP Email Service**
   - **Purpose**: Send inventory alerts and notifications
   - **Configuration**: SMTP server, port (default 587 for TLS), username, password
   - **Library**: smtplib with email.mime

### Python Libraries

- **streamlit**: Web application framework
- **pandas**: Data manipulation and analysis
- **requests**: HTTP client for API calls
- **gspread**: Google Sheets integration
- **google-oauth2**: Authentication for Google services
- **psycopg2**: PostgreSQL database adapter
- **python-dotenv**: Environment variable management

### Database

- **PostgreSQL**: Primary data store for forecast history and analysis
- **Tables**: forecast_runs, forecast_details
- **Connection pattern**: Environment variable-based configuration

### Environment Variables Required

- **Database**: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
- **SmartBill**: SmartBill credentials (email, token, CIF)
- **easySales**: Bearer token
- **Google Sheets**: Service account JSON or credentials path
- **SMTP**: SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD