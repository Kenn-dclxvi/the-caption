from typing import Final
from datetime import datetime
from jinja2 import Template
from src.lib.logger import setup_logger
from src.app.renderer.base import BaseRenderer

logger = setup_logger(__name__)

class AlertRenderer(BaseRenderer):
    __REV: Final[str] = "Rev. 7"
    
    def __init__(self) -> None:
        super().__init__()
        logger.info(f"[{self.__REV}] Initializing AlertRenderer")

    def render(self, message: str, stage: str, is_test: bool) -> str:
        logger.info(f"[Outcome] Alert: Stage='{stage}', IsTest={is_test}")

        template = Template("""
        <!DOCTYPE html><html><body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, sans-serif;">
        <div style="max-width: 440px; margin: auto; padding: 45px 24px;">
            <div style="margin-bottom: 45px;">
                <div style="font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 12px; font-weight: 600;">Status</div>
                <div style="font-size: 32px; font-weight: 200; color: #1e293b; line-height: 1.1;">{{ title }}</div>
                <div style="margin-top: 18px; font-size: 11px; font-weight: 500; color: #1e293b; letter-spacing: 0.1em; line-height: 1.8;">
                    <div><span style="color:#cbd5e1;">DATE</span>&nbsp;&nbsp;{{ date }}</div>
                    <div><span style="color:#cbd5e1;">STAGE</span>&nbsp;&nbsp;{{ stage }}</div>
                    <div style="margin-top: 8px;"><span style="color:#cbd5e1;">ERROR</span></div>
                    <div style="color: #64748b; white-space: pre-wrap; font-size: 10px;">{{ error }}</div>
                </div>
            </div>
            <div style="margin-top: 64px; border-top: 1px solid #f8fafc; padding-top: 24px;"><p style="margin: 0; font-size: 9px; color: #cbd5e1; letter-spacing: 0.1em; text-transform: uppercase;">{{ sender }}</p></div>
        </div></body></html>
        """)
        
        ctx = self.get_common_context()
        ctx.update({
            "title": "SYSTEM TEST" if is_test else "CRITICAL ERROR",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stage": stage,
            "error": message
        })
        return template.render(**ctx)
