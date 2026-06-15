from typing import Final

from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.lib.logger import setup_logger
from src.lib.timeline_controller import TimelineController

logger = setup_logger(__name__)


_JP_SETTLEMENT_CLASSES: Final[set[str]] = {"MUTUAL_FUNDS", "JP_STOCK"}


class V4LedgerFinalizer:
    __REV: Final[str] = "Rev. 1"

    def __init__(self, timeline: TimelineController) -> None:
        logger.info(f"[{self.__REV}] Initializing V4LedgerFinalizer")
        self.__timeline = timeline

    def finalize(self, shadow_ledger: ShadowLedger) -> ShadowLedger:
        target_date = shadow_ledger.target_date
        jp_holiday = self.__timeline.is_holiday(target_date)

        finalized_assets = [
            self.__finalize_asset(asset, target_date, jp_holiday)
            for asset in shadow_ledger.assets
        ]

        if finalized_assets == list(shadow_ledger.assets):
            return shadow_ledger

        return shadow_ledger.model_copy(update={"assets": finalized_assets})

    def __finalize_asset(
        self,
        asset: ShadowAssetRecord,
        target_date: str,
        jp_holiday: bool,
    ) -> ShadowAssetRecord:
        if asset.source == "ABSOLUTE_AMOUNT" or asset.pricing_status == "STATIC":
            return asset.model_copy(update={"diff_val_jpy": 0.0, "diff_pct": 0.0})

        if jp_holiday and asset.asset_class in _JP_SETTLEMENT_CLASSES:
            if asset.diff_val_jpy in (None, 0, 0.0) and asset.diff_pct in (None, 0, 0.0):
                return asset
            logger.info(
                f"[Guard] Finalizing closed JP market asset {asset.name} for {target_date}: diff forced to 0"
            )
            return asset.model_copy(update={"diff_val_jpy": 0.0, "diff_pct": 0.0})

        return asset
