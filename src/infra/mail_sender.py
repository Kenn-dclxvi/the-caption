import smtplib
from typing import Final
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.lib.logger import setup_logger
from src.config.settings import (
    APP_NAME,
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    SMTP_TO
)

logger = setup_logger(__name__)


class MailSender:
    __REV: Final[str] = "Rev. 12"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing MailSender")

    def send(self, subject: str, html_content: str) -> bool:
        if not all([SMTP_SERVER, SMTP_USER, SMTP_PASS, SMTP_TO]):
            logger.error("[Guard] SMTP Configuration is incomplete.")
            return False

        msg = MIMEMultipart()
        msg["From"] = f"{APP_NAME} <{SMTP_USER}>"
        msg["To"] = SMTP_TO
        msg["Subject"] = subject

        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            logger.info(f"[Outcome] Successfully delivered email: {subject}")
            return True
        except Exception as e:
            logger.error(f"[Outcome] Failed to deliver email: {e}")
            return False
