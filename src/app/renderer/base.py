from typing import Dict, Final
from jinja2 import Template
from src.config.settings import APP_NAME, VERSION
from src.lib.logger import setup_logger
from src.app.renderer.view_models import SummaryViewModel

logger = setup_logger(__name__)

class BaseRenderer:
    __REV: Final[str] = "Rev. 9"

    def __init__(self) -> None:
        self.__app_context: Final[str] = f"{APP_NAME} {VERSION}"
        
        self.__c_ink: Final[str] = "#1e293b"
        self.__c_gold: Final[str] = "#c5a059"
        self.__c_slate: Final[str] = "#64748b"
        self.__c_silver: Final[str] = "#cbd5e1"
        self.__c_dawn: Final[str] = "#f8fafc"

    @property
    def app_context(self) -> str:
        return self.__app_context

    @property
    def c_ink(self) -> str:
        return self.__c_ink

    @property
    def c_gold(self) -> str:
        return self.__c_gold

    @property
    def c_slate(self) -> str:
        return self.__c_slate

    @property
    def c_silver(self) -> str:
        return self.__c_silver

    @property
    def c_dawn(self) -> str:
        return self.__c_dawn

    def render_safe_ratio_section(self, summary_vm: SummaryViewModel) -> str:
        return Template("""<div style="margin-bottom: 60px;">
                    <div style="margin-bottom: 24px;">
                        <div style="font-size: 18px; color: {{ c_slate }}; letter-spacing: 0.15em; margin-bottom: 8px; text-transform: uppercase; font-weight: 300; line-height: 1.4;">Safe Ratio</div>
                        <div style="font-size: 60px; font-weight: 100; color: {{ c_ink }}; line-height: 1.0; letter-spacing: -0.04em; margin-left: -2px;">
                            {{ sum.fmt_safe_ratio }}
                        </div>
                    </div>
                    <div style="margin-bottom: 24px; width: 100%;">
                        <div style="width: 100%; height: 12px; background-color: #f1f5f9; overflow: hidden; display: flex;">
                            <div style="width: {{ sum.exposure_width_pct }}%; display: flex;">
                                <div style="width: {{ sum.slate_share }}%; background-color: {{ c_slate }};"></div>
                                <div style="width: {{ sum.gold_share }}%; background-color: {{ c_gold }};"></div>
                            </div>
                            <div style="width: 2px; background-color: #ffffff;"></div>
                            <div style="width: {{ sum.safe_ratio_pct }}%; background-color: {{ c_silver }};"></div>
                        </div>
                    </div>
                    <table border="0" cellpadding="0" cellspacing="0" style="width: 100%;">
                        <tr>
                            <td style="width: 33%; vertical-align: top;">
                                <div style="font-size: 11px; color: {{ c_slate }}; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 4px;">Exposure</div>
                                <div style="font-size: 20px; color: {{ c_ink }}; font-weight: 200; letter-spacing: -0.02em;">{{ sum.fmt_exposure }}</div>
                            </td>
                            <td style="width: 34%; vertical-align: top; text-align: center;">
                                <div style="font-size: 11px; color: {{ c_slate }}; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 4px;">Iron Bank</div>
                                <div style="font-size: 20px; color: {{ c_ink }}; font-weight: 200; letter-spacing: -0.02em;">{{ sum.fmt_iron_bank }}</div>
                            </td>
                            <td style="width: 33%; vertical-align: top; text-align: right;">
                                <div style="font-size: 11px; color: {{ c_slate }}; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 4px;">Total Return</div>
                                <div style="font-size: 20px; color: {{ sum.total_pl_color }}; font-weight: 200; letter-spacing: -0.02em;">{{ sum.fmt_total_pl }}</div>
                            </td>
                        </tr>
                    </table>
                </div>""").render(
            sum=summary_vm,
            c_ink=self.__c_ink,
            c_gold=self.__c_gold,
            c_slate=self.__c_slate,
            c_silver=self.__c_silver,
        )

    def get_common_context(self) -> Dict[str, str]:
        return {
            "sender": self.__app_context,
            "c_ink": self.__c_ink,
            "c_gold": self.__c_gold,
            "c_slate": self.__c_slate,
            "c_silver": self.__c_silver,
            "c_dawn": self.__c_dawn,
        }
