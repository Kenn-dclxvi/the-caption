import json
import os
import tempfile
from typing import Any, Final

from src.config.settings import DIR_CURRENT
from src.lib.logger import setup_logger

logger = setup_logger(__name__)


class MarketSnapshotRepository:
    __REV: Final[str] = "Rev. 1"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing MarketSnapshotRepository")

    def save(self, data: dict[str, Any], target_date: str) -> bool:
        path = self.__get_path(target_date)
        try:
            os.makedirs(DIR_CURRENT, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=DIR_CURRENT, suffix=".json.tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2, ensure_ascii=False)
                    handle.write("\n")
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info(f"[Parsing] Saved market snapshot to {os.path.basename(path)}")
            return True
        except Exception as exc:
            logger.error(f"[Outcome] Failed to save {os.path.basename(path)}: {exc}")
            return False

    def __get_path(self, target_date: str) -> str:
        filename = f"market_snapshot_{target_date.replace('-', '')}.json"
        return os.path.join(DIR_CURRENT, filename)
