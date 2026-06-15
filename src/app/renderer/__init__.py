from typing import Dict, Any, List, Final, Optional
from src.lib.logger import setup_logger
from src.app.renderer.report_fortress import FortressRenderer
from src.app.renderer.report_context import ContextRenderer
from src.app.renderer.report_monthly import MonthlyRenderer
from src.app.renderer.report_collection import CollectionRenderer
from src.app.renderer.alert import AlertRenderer
from src.app.renderer.view_models import SummaryViewModel, PositionViewModel, CollectionSummaryViewModel, CollectionSectionViewModel

logger = setup_logger(__name__)

class ContentRenderer:
    __REV: Final[str] = "Rev. 44"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing ContentRenderer")
        self.__fortress = FortressRenderer()
        self.__context = ContextRenderer()
        self.__monthly = MonthlyRenderer()
        self.__collection = CollectionRenderer()
        self.__alert = AlertRenderer()

    def render_fortress(self, summary_vm: SummaryViewModel, asset_vms: List[PositionViewModel]) -> str:
        logger.info("[Parsing] Rendering Fortress View")
        return self.__fortress.render_vm(summary_vm, asset_vms)

    def render_context(self, data: Dict[str, Any]) -> str:
        logger.info("[Parsing] Rendering Context View")
        return self.__context.render(data)

    def render_monthly(self, data: Dict[str, Any], summary_vm: Optional[SummaryViewModel]) -> str:
        logger.info("[Parsing] Rendering Monthly View")
        if data.get("schema_version") == "v4.1-monthly-chronicle":
            return self.__monthly.render_v4(data, summary_vm)
        if summary_vm is None:
            raise ValueError("summary_vm is required for legacy monthly rendering")
        return self.__monthly.render(data, summary_vm)

    def render_collection(self, summary_vm: CollectionSummaryViewModel, section_vms: List[CollectionSectionViewModel]) -> str:
        logger.info("[Parsing] Rendering Collection View")
        return self.__collection.render(summary_vm, section_vms)

    def render_alert(self, message: str, stage: str, is_test: bool) -> str:
        logger.info("[Parsing] Rendering Alert View")
        return self.__alert.render(message, stage, is_test)
