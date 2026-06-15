from pathlib import Path
from typing import Any, Final

from jinja2 import Template

from src.app.renderer.base import BaseRenderer
from src.app.renderer.v4_view_models import V4MonolithicViewModel
from src.lib.logger import setup_logger

logger = setup_logger(__name__)


class V4ContentRenderer(BaseRenderer):
    __REV: Final[str] = "Rev. 1"

    def __init__(self) -> None:
        super().__init__()
        logger.info(f"[{self.__REV}] Initializing V4ContentRenderer")
        self.__template_path = Path(__file__).resolve().parent / "templates" / "v4_monolithic.html"

    def render(self, vm: V4MonolithicViewModel) -> str:
        logger.info(f"[Outcome] V4 Monolithic render: Date={vm.target_date}, Assets={len(vm.ledger_rows)}")
        template = Template(self.__template_path.read_text(encoding="utf-8"))
        ctx = self.get_common_context()
        ctx.update({"vm": vm})
        rendered = template.render(**ctx)
        if isinstance(rendered, str):
            return rendered
        return self.__render_fallback(vm)

    def __render_fallback(self, vm: V4MonolithicViewModel) -> str:
        def _units_price(row: Any) -> str:
            parts: list[str] = []
            if row.fmt_units:
                parts.append(f"UNITS {row.fmt_units}")
            if row.fmt_price:
                parts.append(f"PRICE {row.fmt_price}")
            if not parts:
                return ""
            return f"<div>{'    '.join(parts)}</div>"

        def _day_line(row: Any) -> str:
            if " / " in row.fmt_day:
                day_value, day_pct = row.fmt_day.split(" / ", 1)
                return (
                    "<div style='white-space:nowrap; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8;'>"
                    f"DAY <span style='color:{row.day_color};'>{day_value}</span> "
                    f"<span style='font-size:11px; color:#64748b;'>/</span> "
                    f"<span style='color:{row.day_color};'>{day_pct}</span>"
                    "</div>"
                )
            return (
                "<div style='white-space:nowrap; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8;'>"
                f"DAY <span style='color:{row.day_color};'>{row.fmt_day}</span>"
                "</div>"
            )

        exposure_rows = "\n".join(
            f"<div style='margin-bottom:60px;'>"
            f"<div style='white-space:nowrap; overflow:hidden; text-overflow:ellipsis'>{row.name}</div>"
            f"<div style='font-size:40px; font-weight:100; color:{row.value_color}'>{row.fmt_value}</div>"
            f"{_units_price(row)}"
            f"<div style='{row.metrics_display_style}'>"
            f"<div>YTD {row.fmt_ytd}&nbsp;&nbsp;&nbsp;&nbsp;MTD {row.fmt_mtd}&nbsp;&nbsp;&nbsp;&nbsp;WTD {row.fmt_wtd}</div>"
            f"{_day_line(row)}"
            "</div>"
            f"<div>{row.day_detail_line}</div></div>"
            for row in vm.exposure_rows
        )
        iron_bank_rows = "\n".join(
            f"<div style='margin-bottom:60px;'>"
            f"<div style='white-space:nowrap; overflow:hidden; text-overflow:ellipsis'>{row.name}</div>"
            f"<div style='font-size:40px; font-weight:100; color:{row.value_color}'>{row.fmt_value}</div>"
            "</div>"
            for row in vm.iron_bank_rows
        )
        appraisal_block = ""
        if vm.show_appraisal:
            appraisal_block = (
                f"<div>{vm.theme_title}</div>"
                f"<div>{vm.theme_subtitle}</div>"
                "<div>State / Primary</div>"
                f"<div>{vm.state_label} / {vm.primary_force}</div>"
            )
        return (
            "<!DOCTYPE html><html lang='ja'><body>"
            f"{appraisal_block}"
            "<div>Safe Ratio</div>"
            f"<div>{vm.fmt_safe_ratio}</div>"
            "<div>Exposure</div>"
            f"<div>{vm.fmt_exposure}</div>"
            "<div>Iron Bank</div>"
            f"<div>{vm.fmt_iron_bank}</div>"
            "<div>Total Return</div>"
            f"<div>{vm.total_return_anchor}</div>"
            "<div>Total Net Assets</div>"
            f"<div>{vm.fmt_total_net_assets}</div>"
            f"<div style='white-space:nowrap; color:#64748b; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8;'><span style='color:#64748b;'>YTD</span>&nbsp;&nbsp;<span style='color:#64748b;'>{vm.ytd_anchor}</span></div>"
            f"<div style='white-space:nowrap; color:#64748b; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8;'><span style='color:#64748b;'>MTD</span>&nbsp;&nbsp;<span style='color:#64748b;'>{vm.total_mtd}</span></div>"
            f"<div style='white-space:nowrap; color:#64748b; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8;'><span style='color:#64748b;'>WTD</span>&nbsp;&nbsp;<span style='color:#64748b;'>{vm.total_wtd}</span></div>"
            f"<div style='white-space:nowrap; color:#64748b; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8; margin-top:2px;'>DAY <span style='color:{vm.day_color};'>{vm.fmt_total_day}</span> <span style='color:#64748b;'>/</span> <span style='color:{vm.day_color};'>{vm.fmt_total_day_pct}</span></div>"
            "<div>Exposure</div>"
            f"{exposure_rows}"
            "<div>Iron Bank</div>"
            f"{iron_bank_rows}"
            "</body></html>"
        )
