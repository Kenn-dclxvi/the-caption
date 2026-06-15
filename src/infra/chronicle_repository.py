import os
import json
import tempfile
from typing import Optional, Dict, Any, Final
from src.config.settings import DIR_CURRENT
from src.lib.logger import setup_logger

logger = setup_logger(__name__)

class ChronicleRepository:
    __REV: Final[str] = "Rev. 3"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing ChronicleRepository")

    def exists(self, year_month: str) -> bool:
        path = self.__get_path(year_month)
        return os.path.exists(path)

    def load(self, year_month: str) -> Optional[Dict[str, Any]]:
        path = self.__get_path(year_month)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"[Parsing] Loaded chronicle cache for {year_month}")
                return data
            except Exception as e:
                logger.error(f"[Outcome] Failed to load {os.path.basename(path)}: {e}")
                return None
        return None

    def save(self, data: Dict[str, Any], year_month: str) -> bool:
        path = self.__get_path(year_month)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=DIR_CURRENT, suffix='.json.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info(f"[Parsing] Saved chronicle cache to {os.path.basename(path)}")
            return True
        except Exception as e:
            logger.error(f"[Outcome] Failed to save {os.path.basename(path)}: {e}")
            return False

    def __get_path(self, year_month: str) -> str:
        filename = f"chronicle_{year_month.replace('-', '')}.json"
        return os.path.join(DIR_CURRENT, filename)
