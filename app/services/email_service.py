"""
app/services/email_service.py
──────────────────────────────
Mock email service for demo purposes.
In production, this would use aiosmtplib or an API like SendGrid/AWS SES.
"""
from app.core.logging import get_logger

logger = get_logger(__name__)

class EmailService:
    @staticmethod
    async def send_share_notification(target_email: str, note_title: str, shared_by: str):
        """
        Simulate sending an email notification when a note is shared.
        """
        logger.info("email_notification_sent", 
                    to=target_email, 
                    subject=f"New note shared: {note_title}",
                    message=f"Hello! {shared_by} has shared a note with you: '{note_title}'.")
        
        # In a real app, you'd do:
        # await aiosmtplib.send(...)
        return True
