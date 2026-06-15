from typing import Final, List
from jinja2 import Template
from src.lib.logger import setup_logger
from src.app.renderer.base import BaseRenderer
from src.app.renderer.view_models import CollectionSummaryViewModel, CollectionSectionViewModel

logger = setup_logger(__name__)

class CollectionRenderer(BaseRenderer):
    __REV: Final[str] = "Rev. 10"

    def __init__(self) -> None:
        super().__init__()
        logger.info(f"[{self.__REV}] Initializing CollectionRenderer")

    def render(self, summary_vm: CollectionSummaryViewModel, section_vms: List[CollectionSectionViewModel]) -> str:
        logger.info(f"[Outcome] Collection: Date={summary_vm.display_date}, Total={summary_vm.fmt_total_value}")
        positions = [pos for section in section_vms for pos in section.positions]
        positions = sorted(positions, key=lambda pos: (-pos.sort_value_jpy, pos.code))

        template = Template("""
        <!DOCTYPE html>
        <html lang="ja">
        <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, sans-serif; -webkit-font-smoothing: antialiased;">
            <div style="max-width: 440px; margin: auto; padding: 45px 24px;">

                <div style="margin-bottom: 60px;">
                    <div style="font-size: 18px; color: {{ c_slate }}; letter-spacing: 0.15em; margin-bottom: 8px; text-transform: uppercase; font-weight: 300; line-height: 1.4;">Exposure</div>
                    <div style="font-size: 60px; font-weight: 100; color: {{ c_ink }}; line-height: 1.0; letter-spacing: -0.04em; margin-left: -2px; margin-bottom: 24px;">
                        {{ sum.fmt_total_value }}
                    </div>
                    <div style="font-size: 14px; font-weight: 300; letter-spacing: 0.05em; color: {{ c_slate }};">
                        <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">DAY</span>&nbsp;&nbsp;<span style="color: {{ sum.day_color }};">{{ sum.fmt_total_diff }}</span>&nbsp;&nbsp;<span style="font-size: 11px; color: {{ c_slate }};">/ {{ sum.fmt_total_diff_pct }}</span></span>
                    </div>
                </div>

                <div style="margin-bottom: 60px;">
                    <div style="border-left: 1px solid {{ c_silver }}; padding-left: 32px; margin-left: 4px; margin-top: 0px;">
                        {% for pos in positions %}
                        <div style="margin-bottom: 60px;">
                            <div style="font-size: 13px; color: {{ c_slate }}; letter-spacing: 0.15em; margin-bottom: 6px; font-weight: 300; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; width: 100%;">
                                {{ pos.name }}
                            </div>
                            <div style="font-size: 40px; font-weight: 100; color: {{ c_ink }}; margin-bottom: 16px; line-height: 1.0; letter-spacing: -0.02em; margin-left: -2px;">
                                {{ pos.fmt_value }}
                            </div>
                            <div style="width: 100%; height: 2px; background-color: #f1f5f9; margin-bottom: 16px;">
                                <div style="width: {{ pos.share_pct }}%; height: 2px; background-color: {{ c_slate }};"></div>
                            </div>
                            <div style="font-size: 12px; font-weight: 300; letter-spacing: 0.05em; color: {{ c_slate }}; line-height: 1.8;">
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">YTD</span>&nbsp;&nbsp;{{ pos.fmt_ytd }}</span>&nbsp;&nbsp;&nbsp;&nbsp;
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">MTD</span>&nbsp;&nbsp;{{ pos.fmt_mtd }}</span>
                            </div>
                            <div style="font-size: 12px; font-weight: 300; letter-spacing: 0.05em; color: {{ c_slate }}; line-height: 1.8; margin-top: 2px;">
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">DAY</span>&nbsp;&nbsp;<span style="color: {{ pos.day_color }};">{{ pos.fmt_diff_jpy }}</span>&nbsp;&nbsp;<span style="font-size: 11px; color: {{ c_slate }};">/</span>&nbsp;&nbsp;<span style="color: {{ pos.day_color }};">{{ pos.fmt_diff_pct }}</span></span>
                            </div>
                            {% if pos.has_day_detail_line %}
                            <div style="font-size: 12px; font-weight: 300; letter-spacing: 0.05em; color: {{ c_slate }}; line-height: 1.8; margin-top: 2px;">
                                <span style="white-space: nowrap;"><span style="color: {{ c_slate }};">USD</span>&nbsp;&nbsp;{{ pos.fmt_usd_value }}</span>&nbsp;&nbsp;&nbsp;&nbsp;
                                <span style="white-space: nowrap;">{{ pos.fx_caption }}</span>
                            </div>
                            {% endif %}
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
        ctx.update({"sum": summary_vm, "positions": positions})
        return template.render(**ctx)
