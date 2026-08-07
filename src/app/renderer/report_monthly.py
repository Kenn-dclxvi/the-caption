from html import escape
from pathlib import Path
from string import Template as StringTemplate
from typing import Dict, Any, Final, Optional
from src.app.renderer.base import BaseRenderer
from src.lib.logger import setup_logger
from src.app.renderer.view_models import SummaryViewModel

logger = setup_logger(__name__)

class MonthlyRenderer(BaseRenderer):
    __REV: Final[str] = "Rev. 11"
    
    def __init__(self) -> None:
        super().__init__()
        logger.info(f"[{self.__REV}] Initializing MonthlyRenderer")
        self.__v4_template_path = Path(__file__).resolve().parent / "templates" / "v4_chronicle.html"
        
    def render(self, data: Dict[str, Any], summary_vm: SummaryViewModel) -> str:
        logger.info("[Parsing] Rendering Monthly Chronicle View")
        
        has_narrative = "theme_title" in data
        
        s_title = f"font-size: 24px; font-weight: 300; line-height: 1.4; color: {self.c_ink}; letter-spacing: 0.1em; font-feature-settings: 'palt'; margin-top: 10px; margin-bottom: 40px;"
        
        s_metric_label = f"font-size: 11px; color: {self.c_slate}; letter-spacing: 0.05em; text-transform: uppercase;"
        s_metric_val = f"font-size: 20px; color: {self.c_ink}; font-weight: 200; margin-top: 4px; letter-spacing: -0.02em;"
        s_metric_val_gold = f"font-size: 20px; color: {summary_vm.total_pl_color}; font-weight: 200; margin-top: 4px; letter-spacing: -0.02em;"
        
        s_card_container = "margin-bottom: 60px;"
        s_card_inner = f"border-left: 1px solid {self.c_silver}; padding-left: 20px; margin-left: 2px;"
        s_body = f"font-size: 15px; font-weight: 300; line-height: 2.0; color: {self.c_ink}; text-align: left; letter-spacing: 0.1em;"
        s_footer = f"margin-top: 64px; border-top: 1px solid #f8fafc; padding-top: 24px; margin-bottom: 0; font-size: 9px; color: {self.c_silver}; letter-spacing: 0.1em; text-transform: uppercase;"

        fortress_html = f"""
        <div style="margin-bottom: 24px;">
            <div style="font-size: 18px; color: {self.c_slate}; letter-spacing: 0.15em; margin-bottom: 8px; text-transform: uppercase; font-weight: 300; line-height: 1.4;">Safe Ratio</div>
            <div style="font-size: 60px; font-weight: 100; color: {self.c_ink}; line-height: 1.0; letter-spacing: -0.04em; margin-left: -2px;">
                {summary_vm.fmt_safe_ratio}
            </div>
        </div>

        <div style="margin-bottom: 24px; width: 100%;">
            <div style="width: 100%; height: 12px; background-color: #f1f5f9; overflow: hidden; display: flex;">
                <div style="width: {summary_vm.exposure_width_pct}%; display: flex;">
                    <div style="width: {summary_vm.slate_share}%; background-color: {self.c_slate};"></div>
                    <div style="width: {summary_vm.gold_share}%; background-color: {self.c_gold};"></div> 
                </div>
                <div style="width: 2px; background-color: #ffffff;"></div>
                <div style="width: {summary_vm.safe_ratio_pct}%; background-color: {self.c_silver};"></div>
            </div>
        </div>
        
        <table border="0" cellpadding="0" cellspacing="0" style="width: 100%;">
            <tr>
                <td style="width: 33%; vertical-align: top;">
                    <div style="{s_metric_label}">Exposure</div>
                    <div style="{s_metric_val}"><span style="white-space: nowrap;">{summary_vm.fmt_exposure}</span></div>
                </td>
                <td style="width: 34%; vertical-align: top; text-align: center;">
                    <div style="{s_metric_label}">Iron Bank</div>
                    <div style="{s_metric_val}"><span style="white-space: nowrap;">{summary_vm.fmt_iron_bank}</span></div>
                </td>
                <td style="width: 33%; vertical-align: top; text-align: right;">
                    <div style="{s_metric_label}">Total Return</div>
                    <div style="{s_metric_val_gold}"><span style="white-space: nowrap;">{summary_vm.fmt_total_pl}</span></div>
                </td>
            </tr>
        </table>
        """

        if has_narrative:
            theme_title = data.get("theme_title", "Monthly Chronicle")
            headline = data.get("chronicle_headline", "")
            body_text = data.get("chronicle_body", "").replace("\n", "<br>")
            shield_review = data.get("shield_review")

            shield_html = ""
            if shield_review:
                shield_html = f"""
                <div style="background-color: {self.c_dawn}; padding: 32px 24px; margin-bottom: 40px;">
                    <div style="font-size: 13px; font-weight: 300; line-height: 1.8; color: {self.c_ink}; letter-spacing: 0.1em;">{shield_review}</div>
                </div>
                """

            narrative_html = f"""
            <div style="{s_title}">{theme_title}</div>
            <div style="{s_card_container}">
                <div style="{s_card_inner}">
                    <div style="font-weight: 300; margin-bottom: 16px; color: {self.c_ink}; font-size: 15px; line-height: 1.6; letter-spacing: 0.1em;">{headline}</div>
                    <div style="{s_body}">{body_text}</div>
                </div>
            </div>
            {shield_html}
            """
        else:
            narrative_html = f"""
            <div style="{s_card_container}">
                <div style="{s_card_inner}">
                    <div style="{s_body}; color: {self.c_slate}; font-style: italic;">*Curator is silent due to insufficient records.*</div>
                </div>
            </div>
            """

        content_html = f"""
        <div style="margin-bottom: 60px;">
            {fortress_html}
        </div>
        {narrative_html}
        <div style="{s_footer}">{self.app_context}</div>
        """
        
        return f"<!DOCTYPE html><html><body style='margin:0;padding:0;background-color:#ffffff;font-family:-apple-system,BlinkMacSystemFont,sans-serif;'><div style='max-width:440px;margin:auto;padding:45px 24px;'>{content_html}</div></body></html>"

    def render_v4(self, data: Dict[str, Any], summary_vm: Optional[SummaryViewModel] = None) -> str:
        logger.info("[V4] Rendering Monthly Chronicle View")

        chronicle = data.get("chronicle", {})
        meta = data.get("meta", {})

        with open(self.__v4_template_path, "r", encoding="utf-8") as fh:
            template = StringTemplate(fh.read())

        safe_ratio_html = ""
        if summary_vm is not None:
            safe_ratio_html = self.__render_v4_safe_ratio(summary_vm)

        context = {
            "year_month": escape(str(meta.get("year_month", ""))),
            "title": escape(str(chronicle.get("title", "Monthly Chronicle"))),
            "overview": self.__html_text(chronicle.get("monthly_summary") or chronicle.get("overview", "")),
            "market_causality": self.__html_text(chronicle.get("market_causality", "")),
            "portfolio_impact": self.__render_v4_list(self.__v4_impact_items(chronicle)),
            "safe_ratio_section": safe_ratio_html,
            "portfolio_audit": self.__html_text(chronicle.get("portfolio_audit") or chronicle.get("structural_change", "")),
            "next_month_watch": self.__render_v4_list(chronicle.get("next_month_watch", [])[:2]),
            "trend_rows": self.__render_v4_trend_rows(self.__top_v4_trends(meta.get("asset_class_trends", []))),
            "app_context": escape(self.app_context),
            "c_ink": self.c_ink,
            "c_gold": self.c_gold,
            "c_slate": self.c_slate,
            "c_silver": self.c_silver,
            "c_dawn": self.c_dawn,
        }
        return template.safe_substitute(context)

    def __render_v4_safe_ratio(self, summary_vm: SummaryViewModel) -> str:
        safe_ratio = escape(summary_vm.fmt_safe_ratio)
        exposure = escape(summary_vm.fmt_exposure)
        iron_bank = escape(summary_vm.fmt_iron_bank)
        total_return = escape(summary_vm.fmt_total_pl)
        return f"""
        <div style="margin-bottom:60px;">
          <div style="margin-bottom:24px;">
            <div style="font-size:18px; color:{self.c_slate}; letter-spacing:0.15em; margin-bottom:8px; text-transform:uppercase; font-weight:300; line-height:1.4;">Safe Ratio</div>
            <div style="font-size:60px; font-weight:100; color:{self.c_ink}; line-height:1.0; letter-spacing:-0.04em; margin-left:-2px;">
              {safe_ratio}
            </div>
          </div>
          <div style="margin-bottom:24px; width:100%;">
            <div style="width:100%; height:12px; background-color:#f1f5f9; overflow:hidden; display:flex;">
              <div style="width:{summary_vm.exposure_width_pct}%; display:flex;">
                <div style="width:{summary_vm.slate_share}%; background-color:{self.c_slate};"></div>
                <div style="width:{summary_vm.gold_share}%; background-color:{self.c_gold};"></div>
              </div>
              <div style="width:2px; background-color:#ffffff;"></div>
              <div style="width:{summary_vm.safe_ratio_pct}%; background-color:{self.c_silver};"></div>
            </div>
          </div>
          <table border="0" cellpadding="0" cellspacing="0" style="width:100%;">
            <tr>
              <td style="width:33%; vertical-align:top;">
                <div style="font-size:11px; color:{self.c_slate}; letter-spacing:0.05em; text-transform:uppercase; margin-bottom:4px;">Exposure</div>
                <div style="font-size:20px; color:{self.c_ink}; font-weight:200; letter-spacing:-0.02em;">{exposure}</div>
              </td>
              <td style="width:34%; vertical-align:top; text-align:center;">
                <div style="font-size:11px; color:{self.c_slate}; letter-spacing:0.05em; text-transform:uppercase; margin-bottom:4px;">Iron Bank</div>
                <div style="font-size:20px; color:{self.c_ink}; font-weight:200; letter-spacing:-0.02em;">{iron_bank}</div>
              </td>
              <td style="width:33%; vertical-align:top; text-align:right;">
                <div style="font-size:11px; color:{self.c_slate}; letter-spacing:0.05em; text-transform:uppercase; margin-bottom:4px;">Total Return</div>
                <div style="font-size:20px; color:{summary_vm.total_pl_color}; font-weight:200; letter-spacing:-0.02em;">{total_return}</div>
              </td>
            </tr>
          </table>
        </div>
        """

    def __v4_impact_items(self, chronicle: Dict[str, Any]) -> list[Any]:
        contributions = chronicle.get("asset_contribution", [])
        phases = chronicle.get("phase_analysis", [])
        if not isinstance(contributions, list):
            contributions = []
        if not isinstance(phases, list):
            phases = []
        return [*contributions, *phases][:3]

    def __top_v4_trends(self, rows: Any) -> list[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []

        def absolute_change(row: Any) -> float:
            if not isinstance(row, dict):
                return 0.0
            try:
                return abs(float(row.get("change_jpy", 0) or 0))
            except (TypeError, ValueError):
                return 0.0

        valid_rows = [row for row in rows if isinstance(row, dict)]
        return sorted(valid_rows, key=absolute_change, reverse=True)[:3]

    def __html_text(self, value: Any) -> str:
        return escape(str(value)).replace("\n", "<br>")

    def __render_v4_trend_rows(self, rows: Any) -> str:
        if not rows:
            return ""

        html_rows = []
        for row in rows:
            source = escape(str(row.get("source") or ""))
            asset_class = escape(str(row.get("asset_class", "")))
            end_value = row.get("end_value_jpy", 0)
            change = row.get("change_jpy", 0)
            share = row.get("end_share_pct", 0.0)
            # source 区分が付かない月（v3 系台帳）は区切りごと省き、空欄を見せない。
            meta_line = " / ".join(
                part for part in (source, f"{share:.2f}%", f"{change:+,.0f} JPY") if part
            )
            html_rows.append(
                f"""
                <div style="margin-bottom:24px;">
                  <div style="font-size:13px; color:{self.c_slate}; letter-spacing:0.15em; margin-bottom:6px; font-weight:300; text-transform:uppercase; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; width:100%;">{asset_class}</div>
                  <div style="font-size:30px; font-weight:100; color:{self.c_ink}; margin-bottom:10px; line-height:1.0; letter-spacing:-0.02em; margin-left:-2px;">{end_value:,.0f}</div>
                  <div style="font-size:12px; font-weight:300; letter-spacing:0.05em; color:{self.c_slate}; line-height:1.8;">
                    <span style="white-space:nowrap;">{meta_line}</span>
                  </div>
                </div>
                """
            )
        return "".join(html_rows)

    def __render_v4_list(self, rows: Any) -> str:
        if not rows:
            return ""
        html_rows = []
        for row in rows:
            if isinstance(row, dict):
                text = " / ".join(str(value) for value in row.values() if value not in (None, ""))
            else:
                text = str(row)
            html_rows.append(
                f"<div style=\"font-size:13px; font-weight:300; line-height:1.8; color:{self.c_ink}; letter-spacing:0.05em; margin-bottom:10px;\">{escape(text)}</div>"
            )
        return "".join(html_rows)
