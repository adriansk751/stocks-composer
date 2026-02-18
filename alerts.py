import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
import os
import pandas as pd


class EmailAlertSystem:
    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None
    ):
        """
        Initialize email alert system.
        
        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP port (usually 587 for TLS)
            smtp_user: SMTP username
            smtp_password: SMTP password
        """
        self.smtp_server = smtp_server or os.getenv("SMTP_SERVER")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
    
    def send_alert(
        self,
        to_emails: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Send an email alert.
        
        Args:
            to_emails: List of recipient email addresses
            subject: Email subject
            body: Plain text email body
            html_body: Optional HTML email body
        
        Returns:
            True if successful, False otherwise
        """
        if not all([self.smtp_server, self.smtp_user, self.smtp_password]):
            print("Email configuration incomplete. Cannot send alert.")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_user
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            return True
        
        except Exception as e:
            print(f"Error sending email: {e}")
            return False
    
    def send_low_stock_alert(
        self,
        to_emails: List[str],
        critical_items: pd.DataFrame,
        forecast_horizon_months: int = 3,
        threshold_qty: float = 0
    ) -> bool:
        """
        Send alert for low stock items.
        
        Args:
            to_emails: List of recipient email addresses
            critical_items: DataFrame with critical items
            forecast_horizon_months: Forecast horizon used
            threshold_qty: Minimum quantity threshold
        
        Returns:
            True if successful, False otherwise
        """
        if critical_items.empty:
            return False
        
        subject = f"⚠️ Low Stock Alert - {len(critical_items)} items need ordering"
        
        body = f"""
Inventory Forecast Low Stock Alert
===================================

{len(critical_items)} products have stock levels below the {forecast_horizon_months}-month forecast requirement.

Top 10 Critical Items:
"""
        
        top_10 = critical_items.head(10)
        for _, row in top_10.iterrows():
            body += f"\n- {row['SKU']}: {row.get('Product Name', 'Unknown')} - Required: {row.get(f'Required {forecast_horizon_months}M', 0):.0f} {row.get('Unit', 'units')}"
        
        if len(critical_items) > 10:
            body += f"\n\n... and {len(critical_items) - 10} more items"
        
        body += "\n\nPlease review the full forecast report for details."
        
        html_body = f"""
<html>
  <body>
    <h2>⚠️ Inventory Forecast Low Stock Alert</h2>
    <p><strong>{len(critical_items)} products</strong> have stock levels below the {forecast_horizon_months}-month forecast requirement.</p>
    
    <h3>Top 10 Critical Items:</h3>
    <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
      <tr style="background-color: #f0f0f0;">
        <th>SKU</th>
        <th>Product Name</th>
        <th>Current Stock</th>
        <th>Daily Sales</th>
        <th>Required ({forecast_horizon_months}M)</th>
      </tr>
"""
        
        for _, row in top_10.iterrows():
            html_body += f"""
      <tr>
        <td>{row['SKU']}</td>
        <td>{row.get('Product Name', 'Unknown')}</td>
        <td>{row.get('Current Stock', 0):.2f}</td>
        <td>{row.get('Daily Sales', 0):.4f}</td>
        <td style="color: red; font-weight: bold;">{row.get(f'Required {forecast_horizon_months}M', 0):.2f}</td>
      </tr>
"""
        
        html_body += """
    </table>
"""
        
        if len(critical_items) > 10:
            html_body += f"<p><em>... and {len(critical_items) - 10} more items</em></p>"
        
        html_body += """
    <p>Please review the full forecast report for complete details.</p>
  </body>
</html>
"""
        
        return self.send_alert(to_emails, subject, body, html_body)


def get_alert_system() -> Optional[EmailAlertSystem]:
    """
    Create email alert system from environment variables.
    
    Returns:
        EmailAlertSystem instance or None if not configured
    """
    if not os.getenv("SMTP_SERVER"):
        return None
    
    return EmailAlertSystem()
