"""
Notification Service Module

This module provides functionality to send notifications about match results
via email (SendGrid/Mailgun) and webhooks. It formats match results into
readable notifications and handles sending through different channels.

The service includes:
- Email notifications via SendGrid
- Email notifications via Mailgun
- Webhook notifications via HTTP POST
- Templating for notification content
- Error handling and logging
"""

import logging
import json
import time
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent
import requests

from app.core.config import settings
from app.models.location import MatchResult, AddressInput

# Configure logger
logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Exception raised for errors in the notification process."""
    pass


class NotificationService:
    """
    Service for sending notifications about match results.
    
    This service sends notifications via email (SendGrid/Mailgun) and webhooks
    based on match results.
    """
    
    def __init__(self):
        """Initialize the notification service."""
        self.notification_method = settings.NOTIFICATION_METHOD
        self._http_client = httpx.AsyncClient(timeout=10.0)
        logger.info(f"Notification service initialized with method: {self.notification_method}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with client cleanup."""
        await self._http_client.aclose()
    
    async def send_notification(
        self, 
        match_result: MatchResult, 
        address_input: AddressInput
    ) -> Dict[str, Any]:
        """
        Send notification based on match result.
        
        Args:
            match_result: The match result to send notification about
            address_input: The original address input with contact information
            
        Returns:
            Dict with notification status and details
            
        Raises:
            NotificationError: If sending notification fails
        """
        start_time = time.time()
        logger.info(f"Sending notification for match result to {address_input.email}")
        
        results = {}
        
        try:
            # Determine which notification methods to use
            if self.notification_method == "email":
                results["email"] = await self._send_email_notification(match_result, address_input)
            elif self.notification_method == "webhook":
                results["webhook"] = await self._send_webhook_notification(match_result, address_input)
            elif self.notification_method == "both":
                results["email"] = await self._send_email_notification(match_result, address_input)
                results["webhook"] = await self._send_webhook_notification(match_result, address_input)
            else:
                raise NotificationError(f"Unsupported notification method: {self.notification_method}")
            
            # Log notification time
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"Notification sent in {elapsed:.2f}ms")
            
            return {
                "status": "success",
                "method": self.notification_method,
                "results": results,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")
            raise NotificationError(f"Failed to send notification: {str(e)}")
    
    async def _send_email_notification(
        self, 
        match_result: MatchResult, 
        address_input: AddressInput
    ) -> Dict[str, Any]:
        """
        Send email notification about match result.
        
        Args:
            match_result: The match result to send notification about
            address_input: The original address input with contact information
            
        Returns:
            Dict with email notification status and details
            
        Raises:
            NotificationError: If sending email notification fails
        """
        # Check if SendGrid API key is configured
        if settings.SENDGRID_API_KEY:
            return await self._send_sendgrid_email(match_result, address_input)
        # Check if Mailgun API key is configured
        elif settings.MAILGUN_API_KEY:
            return await self._send_mailgun_email(match_result, address_input)
        else:
            raise NotificationError("No email service configured (SendGrid or Mailgun)")
    
    async def _send_sendgrid_email(
        self, 
        match_result: MatchResult, 
        address_input: AddressInput
    ) -> Dict[str, Any]:
        """
        Send email notification using SendGrid.
        
        Args:
            match_result: The match result to send notification about
            address_input: The original address input with contact information
            
        Returns:
            Dict with SendGrid email notification status and details
            
        Raises:
            NotificationError: If sending SendGrid email notification fails
        """
        logger.info(f"Sending SendGrid email to {address_input.email}")
        
        try:
            # Get API key
            api_key = settings.SENDGRID_API_KEY.get_secret_value()
            
            # Create email content
            subject = settings.EMAIL_SUBJECT_TEMPLATE.format(
                hub_name=match_result.matched_location.name
            )
            
            # Create HTML email content
            html_content = self._create_email_html_content(match_result, address_input)
            
            # Create SendGrid mail object
            message = Mail(
                from_email=Email(settings.EMAIL_FROM),
                to_emails=To(address_input.email),
                subject=subject,
                html_content=HtmlContent(html_content)
            )
            
            # Add admin as CC if configured
            if settings.EMAIL_ADMIN:
                message.add_cc(settings.EMAIL_ADMIN)
            
            # Send email
            sg = SendGridAPIClient(api_key)
            response = sg.send(message)
            
            logger.info(f"SendGrid email sent with status code: {response.status_code}")
            
            return {
                "provider": "sendgrid",
                "status_code": response.status_code,
                "message_id": response.headers.get("X-Message-Id", ""),
                "recipient": address_input.email
            }
            
        except Exception as e:
            logger.error(f"SendGrid email error: {str(e)}")
            raise NotificationError(f"SendGrid email error: {str(e)}")
    
    async def _send_mailgun_email(
        self, 
        match_result: MatchResult, 
        address_input: AddressInput
    ) -> Dict[str, Any]:
        """
        Send email notification using Mailgun.
        
        Args:
            match_result: The match result to send notification about
            address_input: The original address input with contact information
            
        Returns:
            Dict with Mailgun email notification status and details
            
        Raises:
            NotificationError: If sending Mailgun email notification fails
        """
        logger.info(f"Sending Mailgun email to {address_input.email}")
        
        try:
            # Get API key and domain
            api_key = settings.MAILGUN_API_KEY.get_secret_value()
            domain = settings.MAILGUN_DOMAIN
            
            if not domain:
                raise NotificationError("Mailgun domain not configured")
            
            # Create email content
            subject = settings.EMAIL_SUBJECT_TEMPLATE.format(
                hub_name=match_result.matched_location.name
            )
            
            # Create HTML email content
            html_content = self._create_email_html_content(match_result, address_input)
            
            # Prepare recipients
            recipients = [address_input.email]
            if settings.EMAIL_ADMIN:
                recipients.append(settings.EMAIL_ADMIN)
            
            # Send email via Mailgun API
            response = requests.post(
                f"https://api.mailgun.net/v3/{domain}/messages",
                auth=("api", api_key),
                data={
                    "from": settings.EMAIL_FROM,
                    "to": recipients,
                    "subject": subject,
                    "html": html_content
                }
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            logger.info(f"Mailgun email sent with status code: {response.status_code}")
            
            return {
                "provider": "mailgun",
                "status_code": response.status_code,
                "message_id": response_data.get("id", ""),
                "recipient": address_input.email
            }
            
        except Exception as e:
            logger.error(f"Mailgun email error: {str(e)}")
            raise NotificationError(f"Mailgun email error: {str(e)}")
    
    async def _send_webhook_notification(
        self, 
        match_result: MatchResult, 
        address_input: AddressInput
    ) -> Dict[str, Any]:
        """
        Send webhook notification about match result.
        
        Args:
            match_result: The match result to send notification about
            address_input: The original address input with contact information
            
        Returns:
            Dict with webhook notification status and details
            
        Raises:
            NotificationError: If sending webhook notification fails
        """
        logger.info("Sending webhook notification")
        
        # Check if webhook URL is configured
        if not settings.WEBHOOK_URL:
            raise NotificationError("Webhook URL not configured")
        
        webhook_url = settings.WEBHOOK_URL
        
        try:
            # Prepare webhook payload
            payload = {
                "match_result": match_result.dict(),
                "address_input": address_input.dict(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Add webhook secret if configured
            headers = {"Content-Type": "application/json"}
            if settings.WEBHOOK_SECRET:
                headers["X-Webhook-Secret"] = settings.WEBHOOK_SECRET.get_secret_value()
            
            # Send webhook request
            response = await self._http_client.post(
                webhook_url,
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            
            logger.info(f"Webhook notification sent with status code: {response.status_code}")
            
            return {
                "status_code": response.status_code,
                "webhook_url": webhook_url,
                "response": response.text
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook HTTP error: {e.response.status_code} - {e.response.text}")
            raise NotificationError(f"Webhook HTTP error: {e.response.status_code}")
            
        except httpx.RequestError as e:
            logger.error(f"Webhook request error: {str(e)}")
            raise NotificationError(f"Webhook request failed: {str(e)}")
            
        except Exception as e:
            logger.error(f"Webhook notification error: {str(e)}")
            raise NotificationError(f"Webhook notification error: {str(e)}")
    
    def _create_email_html_content(
        self, 
        match_result: MatchResult, 
        address_input: AddressInput
    ) -> str:
        """
        Create HTML content for email notification.
        
        Args:
            match_result: The match result to include in the email
            address_input: The original address input
            
        Returns:
            HTML content as string
        """
        # Get applicant name or use email as fallback
        applicant_name = address_input.name or address_input.email.split('@')[0]
        
        # Format distance in miles with 1 decimal place
        distance_miles = round(match_result.distance_miles, 1)
        
        # Create HTML content
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #f8f8f8;
                    padding: 20px;
                    border-bottom: 2px solid #ddd;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                }}
                .location-details {{
                    background-color: #f0f7ff;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    font-size: 12px;
                    color: #777;
                    border-top: 1px solid #ddd;
                    padding-top: 20px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Your Nearest Delivery Hub</h2>
            </div>
            <div class="content">
                <p>Hello {applicant_name},</p>
                
                <p>Thank you for your interest in joining our delivery team. We've found the nearest delivery hub to your location:</p>
                
                <div class="location-details">
                    <h3>{match_result.matched_location.name}</h3>
                    <p><strong>Address:</strong> {match_result.matched_location.address}</p>
                    <p><strong>Distance:</strong> {distance_miles} miles from your location</p>
                </div>
                
                <p>Your application will be forwarded to this hub's management team, who will contact you with next steps.</p>
                
                <p>If you have any questions, please don't hesitate to contact our support team.</p>
                
                <p>Best regards,<br>The Delivery Team</p>
            </div>
            <div class="footer">
                <p>This is an automated message. Please do not reply to this email.</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def format_match_result_text(
        self, 
        match_result: MatchResult, 
        address_input: AddressInput
    ) -> str:
        """
        Format match result as plain text for notifications.
        
        Args:
            match_result: The match result to format
            address_input: The original address input
            
        Returns:
            Formatted text
        """
        # Format distance in miles with 1 decimal place
        distance_miles = round(match_result.distance_miles, 1)
        
        text = f"""
        Nearest Delivery Hub Match Result
        
        Input Address: {match_result.input_address}
        Geocoded Address: {match_result.geocoded_address}
        
        Nearest Delivery Hub:
        - Name: {match_result.matched_location.name}
        - Address: {match_result.matched_location.address}
        - Distance: {distance_miles} miles
        
        Applicant Information:
        - Name: {address_input.name or "Not provided"}
        - Email: {address_input.email}
        - Phone: {address_input.phone or "Not provided"}
        - Application ID: {address_input.application_id or "Not provided"}
        
        Timestamp: {match_result.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}
        """
        
        return text
