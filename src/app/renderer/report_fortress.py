from typing import Final, List
from jinja2 import Template
from src.lib.logger import setup_logger
from src.app.renderer.base import BaseRenderer
from src.app.renderer.view_models import SummaryViewModel, PositionViewModel

logger = setup_logger(__name__)

class FortressRenderer(BaseRenderer):
    __REV: Final[str] = "Rev. 28"
    
    def __init__(self) -> None:
        super().__init__()
        logger.info(f"[{self.__REV}] Initializing FortressRenderer")

    def render_vm(self, summary_vm: SummaryViewModel, asset_vms: List[PositionViewModel]) -> str:
        logger.info(f"[Outcome] Fortress: SafeRatio={summary_vm.fmt_safe_ratio}, WTD={summary_vm.total_wtd}")

        safe_ratio_html = self.render_safe_ratio_section(summary_vm)

        template = Template("""
        <!DOCTYPE html>
        <html lang="ja">
        <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, sans-serif; -webkit-font-smoothing: antialiased;">
            <div style="max-width: 440px; margin: auto; padding: 45px 24px;">

                {{ safe_ratio_html }}

                <div style="border-left: 1px solid {{ c_silver }}; padding-left: 32px; margin-left: 4px;">
                    <div style="margin-bottom: 60px;">
                        <div style="font-size: 18px; color: {{ c_slate }}; letter-spacing: 0.15em; margin-bottom: 8px; text-transform: uppercase; font-weight: 300; line-height: 1.4;">Exposure</div>
                        <div style="font-size: 60px; font-weight: 100; letter-spacing: -0.04em; color: {{ c_ink }}; line-height: 1.0; margin-bottom: 24px; margin-left: -4px;">
                            {{ sum.fmt_exposure }}
                        </div>
                        
                        <div style="font-size: 16px; font-weight: 300; color: {{ c_slate }}; margin-bottom: 6px; letter-spacing: 0.05em;">
                            <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">YTD</span>&nbsp;&nbsp;{{ sum.total_ytd }}</span>&nbsp;&nbsp;&nbsp;&nbsp;
                            <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">MTD</span>&nbsp;&nbsp;{{ sum.total_mtd }}</span>&nbsp;&nbsp;&nbsp;&nbsp;
                            <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">WTD</span>&nbsp;&nbsp;{{ sum.total_wtd }}</span>
                        </div>
                        
                        <div style="font-size: 13px; font-weight: 300; color: {{ c_slate }}; letter-spacing: 0.05em; margin-top: 8px;">
                            <span style="white-space: nowrap;">DAY&nbsp;&nbsp;{{ sum.fmt_total_diff }} <span style="font-size: 11px; margin: 0 4px;">/</span> {{ sum.fmt_total_diff_pct }}</span>
                        </div>
                    </div>

                    <div style="margin-top: 0px;">
                        {% for a in assets %}
                        <div style="margin-bottom: 60px;">
                            <div style="font-size: 13px; color: {{ c_slate }}; letter-spacing: 0.15em; margin-bottom: 6px; font-weight: 300; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; width: 100%;">
                                {{ a.label }}
                            </div>
                            <div style="font-size: 40px; font-weight: 100; color: {{ c_ink }}; margin-bottom: 16px; line-height: 1.0; letter-spacing: -0.02em; margin-left: -2px;">
                                {{ a.fmt_value }}
                            </div>
                            <div style="width: 100%; height: 2px; background-color: #f1f5f9; margin-bottom: 16px;">
                                <div style="width: {{ a.share_pct }}%; height: 2px; background-color: {{ c_slate }};"></div>
                            </div>
                            <div style="font-size: 12px; font-weight: 300; letter-spacing: 0.05em; color: {{ c_slate }}; line-height: 1.8; {{ a.metrics_display_style }}">
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">YTD</span>&nbsp;&nbsp;{{ a.ytd }}</span>&nbsp;&nbsp;&nbsp;&nbsp;
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">MTD</span>&nbsp;&nbsp;{{ a.mtd }}</span>&nbsp;&nbsp;&nbsp;&nbsp;
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">WTD</span>&nbsp;&nbsp;{{ a.wtd }}</span>&nbsp;&nbsp;&nbsp;&nbsp;
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">DAY</span>&nbsp;&nbsp;{{ a.fmt_diff_jpy }} <span style="font-size: 11px; margin: 0 4px;">/</span> {{ a.fmt_diff_pct }}</span>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                
                <div style="margin-top: 60px; border-top: 1px solid #f8fafc; padding-top: 24px;">
                    <p style="margin: 0; font-size: 9px; color: {{ c_silver }}; letter-spacing: 0.1em; text-transform: uppercase;">{{ sender }}</p>
                </div>
            </div>
        </body>
        </html>
        """)
        
        ctx = self.get_common_context()
        ctx.update({"sum": summary_vm, "assets": asset_vms, "safe_ratio_html": safe_ratio_html})

        return template.render(**ctx)
