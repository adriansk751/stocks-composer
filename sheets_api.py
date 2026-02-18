import logging
import gspread
from google.oauth2.service_account import Credentials
from typing import Dict, Optional
import os
import json

logger = logging.getLogger(__name__)


class GoogleSheetsAPI:
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    def __init__(self, credentials_path: Optional[str] = None, credentials_json: Optional[str] = None):
        """
        Initialize Google Sheets API client.
        
        Args:
            credentials_path: Path to service account JSON file
            credentials_json: JSON string containing service account credentials
        """
        if credentials_json:
            creds_dict = json.loads(credentials_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=self.SCOPES)
        elif credentials_path and os.path.exists(credentials_path):
            creds = Credentials.from_service_account_file(credentials_path, scopes=self.SCOPES)
        else:
            raise ValueError("No valid credentials provided for Google Sheets API")
        
        self.client = gspread.authorize(creds)
    
    def get_incoming_quantities(
        self, 
        sheet_id: str, 
        worksheet_name: str = "Sheet1",
        sku_column: str = "SKU",
        incoming_column: str = "Incoming"
    ) -> Dict[str, float]:
        """
        Read incoming quantities from Google Sheets.
        
        Args:
            sheet_id: Google Sheets spreadsheet ID
            worksheet_name: Name of the worksheet
            sku_column: Name of the column containing SKU codes
            incoming_column: Name of the column containing incoming quantities
        
        Returns:
            Dictionary mapping SKU to incoming quantity
        """
        try:
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)
            
            all_records = worksheet.get_all_records()
            
            incoming_data = {}
            for record in all_records:
                sku = record.get(sku_column)
                incoming = record.get(incoming_column)
                
                if sku:
                    try:
                        incoming_qty = float(incoming) if incoming else 0
                        incoming_data[str(sku)] = incoming_qty
                    except (ValueError, TypeError):
                        incoming_data[str(sku)] = 0
            
            return incoming_data
            
        except Exception as e:
            logger.error(f"Error reading from Google Sheets: {e}")
            return {}


def get_sheets_client() -> Optional[GoogleSheetsAPI]:
    """
    Create Google Sheets API client from environment variables.
    
    Returns:
        GoogleSheetsAPI instance or None if credentials not found
    """
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    
    if not creds_path and not creds_json:
        return None
    
    try:
        return GoogleSheetsAPI(
            credentials_path=creds_path,
            credentials_json=creds_json
        )
    except Exception as e:
        logger.error(f"Error creating Google Sheets client: {e}")
        return None
