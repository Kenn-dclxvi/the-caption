import html
from datetime import datetime
from typing import Dict, Any, Final
from src.app.renderer.base import BaseRenderer
from src.lib.logger import setup_logger

logger = setup_logger(__name__)

class ContextRenderer(BaseRenderer):
    __REV: Final[str] = "Rev. 23"
    
    def __init__(self) -> None:
        super().__init__()
        logger.info(f"[{self.__REV}] Initializing ContextRenderer")

    def render(self, data: Dict[str, Any]) -> str:
        is_exhibition = "theme" in data
        
        theme_title = data.get('theme', 'N/A')
        items_count = len(data.get('featured_assets', []))
        insight_len = len(data.get('implication', ''))
        logger.info(f"[Outcome] Context: Theme='{theme_title}', Items={items_count}, InsightLen={insight_len}")
        
        if is_exhibition:
            meta = data.get("meta", {})
            
            s_theme = f"font-size: 24px; font-weight: 300; line-height: 1.4; color: {self.c_ink}; letter-spacing: 0.1em; font-feature-settings: 'palt'; margin-top: 10px; margin-bottom: 40px;"
            s_card_container = "margin-bottom: 60px;"
            s_card_inner = f"border-left: 1px solid {self.c_silver}; padding-left: 20px; margin-left: 2px;"
            s_body = f"font-size: 15px; font-weight: 300; line-height: 2.0; color: {self.c_ink}; text-align: left; letter-spacing: 0.1em;"
            s_gallery_container = "margin-bottom: 60px;"
            s_asset_row = "margin-bottom: 32px;"
            s_asset_head = "margin-bottom: 6px;"
            s_asset_name = f"font-size: 13px; font-weight: 300; color: {self.c_ink}; letter-spacing: 0.1em; margin-right: 8px;"
            s_asset_meta = f"font-size: 12px; font-weight: 300; color: {self.c_slate}; letter-spacing: 0.1em; white-space: nowrap;"
            s_asset_cap = f"font-size: 13px; font-weight: 300; line-height: 1.7; color: {self.c_ink}; letter-spacing: 0.1em;"
            s_insight_container = f"background-color: {self.c_dawn}; padding: 32px 24px; margin-bottom: 40px;"
            s_insight_text = f"font-size: 13px; font-weight: 300; line-height: 1.8; color: {self.c_ink}; letter-spacing: 0.1em;"
            s_audit_container = f"border-bottom: 1px solid {self.c_silver}; padding-bottom: 18px; margin-bottom: 24px;"
            s_audit_label = f"font-size: 11px; font-weight: 300; line-height: 1.4; color: {self.c_slate}; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 10px;"
            s_audit_status = f"font-size: 12px; font-weight: 300; line-height: 1.6; color: {self.c_slate}; letter-spacing: 0.05em; margin-bottom: 8px;"
            s_audit_text = f"font-size: 13px; font-weight: 300; line-height: 1.7; color: {self.c_ink}; letter-spacing: 0.05em;"
            s_footer_container = "margin-top: 64px; border-top: 1px solid #f8fafc; padding-top: 24px;"
            s_footer_text = f"margin: 0; font-size: 9px; color: {self.c_silver}; letter-spacing: 0.1em; text-transform: uppercase; text-align: left;"

            id_data_map = data.get("_ledger_data", {})
            gallery_html = ""
            works = data.get("featured_assets", [])

            for item in works:
                asset_id = item.get("asset_id", "")
                caption = item.get("caption", "")
                actual = id_data_map.get(asset_id)
                if actual:
                    name = html.escape(actual["name"])
                    raw_meta = f"Share: {actual['share_pct']:.1f}% | Diff: {actual['diff_pct']:+.2f}%"
                    if actual.get("wtd", "---") not in ("---", ""):
                        raw_meta += f" | WTD: {html.escape(str(actual['wtd']))}"
                else:
                    logger.warning(f"[Guard] Unknown asset_id from AI: '{asset_id}'")
                    name = html.escape(asset_id) if asset_id else "Unknown Asset"
                    raw_meta = ""

                meta_info = html.escape(raw_meta).replace("|", f"<span style='color: {self.c_silver}; margin: 0 4px;'>|</span>")
                
                gallery_html += f"""
                <div style="{s_asset_row}">
                    <div style="{s_asset_head}">
                        <span style="{s_asset_name}">{name}</span>
                        <span style="{s_asset_meta}">{meta_info}</span>
                    </div>
                    <div style="{s_asset_cap}">{html.escape(caption)}</div>
                </div>
                """

            overview_html = html.escape(data.get("overview", "")).replace("\n", "<br>")

            portfolio_audit = data.get("portfolio_audit")
            portfolio_audit_html = ""
            if isinstance(portfolio_audit, dict):
                raw_core_thesis = str(portfolio_audit.get("core_thesis", "")).strip()
                raw_cash_buffer = str(portfolio_audit.get("cash_buffer", "")).strip()
                raw_stagnation = str(portfolio_audit.get("stagnation_readiness", "")).strip()
                raw_summary = str(portfolio_audit.get("summary", "")).strip()
                core_thesis = html.escape(raw_core_thesis)
                cash_buffer = html.escape(raw_cash_buffer)
                stagnation = html.escape(raw_stagnation)
                audit_summary = html.escape(raw_summary).replace("\n", "<br>")
                status_parts = []
                if core_thesis:
                    status_parts.append(f"Core Thesis: {core_thesis}")
                if cash_buffer:
                    status_parts.append(f"Cash: {cash_buffer}")
                if stagnation:
                    status_parts.append(f"Stagnation: {stagnation}")
                status_html = " / ".join(status_parts)
                if status_html or audit_summary:
                    portfolio_audit_html = f"""
                    <div style="{s_audit_container}">
                        <div style="{s_audit_label}">Portfolio Audit</div>
                        <div style="{s_audit_status}">{status_html}</div>
                        <div style="{s_audit_text}">{audit_summary}</div>
                    </div>
                    """

            shield_eval = data.get("shield_evaluation")
            shield_html = ""
            if shield_eval:
                shield_eval_safe = html.escape(shield_eval).replace("\n", "<br>")
                shield_html = f"""
                <div style="margin-top: 24px; border-top: 1px solid {self.c_silver}; padding-top: 16px;">
                    <div style="font-size: 13px; font-weight: 300; line-height: 1.6; color: {self.c_slate}; letter-spacing: 0.05em;">
                        {shield_eval_safe}
                    </div>
                </div>
                """

            content_html = f"""
            <div style="{s_theme}">{html.escape(data.get("theme", ""))}</div>

            <div style="{s_card_container}">
                <div style="{s_card_inner}">
                    <div style="{s_body}">{overview_html}</div>
                </div>
            </div>

            <div style="{s_gallery_container}">
                {gallery_html}
            </div>

            <div style="{s_insight_container}">
                {portfolio_audit_html}
                <div style="{s_insight_text}">{html.escape(data.get("implication", ""))}</div>
                {shield_html}
            </div>

            <div style="{s_footer_container}">
                <p style="{s_footer_text}">{self.app_context}</p>
            </div>
            """

        else:
            logger.warning("[Guard] Non-exhibition data received. Rendering minimal fallback.")
            content_html = f"""
            <div style="font-size: 15px; font-weight: 300; color: {self.c_ink}; padding: 40px 0;">
                <div style="margin-bottom: 20px; color: {self.c_slate};">INVALID DATA STRUCTURE</div>
                <div>The provided context data does not match the Exhibition format.</div>
            </div>
            """
        
        return f"<!DOCTYPE html><html><body style='margin:0;padding:0;background-color:#ffffff;font-family:-apple-system,BlinkMacSystemFont,sans-serif;'><div style='max-width:440px;margin:auto;padding:45px 24px;'>{content_html}</div></body></html>"
