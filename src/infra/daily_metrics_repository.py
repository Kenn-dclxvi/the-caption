import json
import os
import tempfile
from typing import Any, Final

from src.config.settings import DIR_CURRENT
from src.lib.logger import setup_logger

logger = setup_logger(__name__)


class DailyMetricsRepository:
    __REV: Final[str] = "Rev. 1"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing DailyMetricsRepository")

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
            logger.info(f"[Parsing] Saved daily metrics to {os.path.basename(path)}")
            return True
        except Exception as exc:
            logger.error(f"[Outcome] Failed to save {os.path.basename(path)}: {exc}")
            return False

    def load_month(self, year_month: str) -> list[dict[str, Any]]:
        if not os.path.exists(DIR_CURRENT):
            return []
        prefix = f"daily_metrics_{year_month.replace('-', '')}"
        records: list[dict[str, Any]] = []
        for filename in sorted(os.listdir(DIR_CURRENT)):
            if not filename.startswith(prefix) or not filename.endswith(".json"):
                continue
            path = os.path.join(DIR_CURRENT, filename)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    records.append(json.load(handle))
            except Exception as exc:
                logger.warning(f"[V4] Skipping unreadable daily metrics: {filename} ({exc})")
        return records

    def __get_path(self, target_date: str) -> str:
        filename = f"daily_metrics_{target_date.replace('-', '')}.json"
        return os.path.join(DIR_CURRENT, filename)
