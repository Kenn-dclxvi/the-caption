import os
import json
import re
import tempfile
from typing import Optional, Set, Dict, Any, Final
from src.config.settings import DIR_CURRENT
from src.lib.logger import setup_logger
from src.lib.models import Ledger
from src.domain.ledger_schema import validate_ledger_dict

logger = setup_logger(__name__)

class LedgerRepository:
    __REV: Final[str] = "Rev. 9"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing LedgerRepository")

    def __filename_for(self, date_str: str) -> str:
        return f"ledger_{date_str.replace('-', '')}.json"

    def load(self, date_str: str) -> Optional[Dict[str, Any]]:
        filename = self.__filename_for(date_str)
        path = os.path.join(DIR_CURRENT, filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not validate_ledger_dict(data, source=filename):
                    logger.error(f"[Guard] Rejecting {filename}: schema invalid")
                    return None
                return data
            except Exception as e:
                logger.error(f"[Outcome] Failed to load {filename}: {e}")
                return None
        return None

    def save(self, ledger: Ledger, date_str: str) -> None:
        self.save_document(ledger.to_dict(), date_str)

    def save_document(self, document: Dict[str, Any], date_str: str) -> None:
        filename = self.__filename_for(date_str)
        save_path = os.path.join(DIR_CURRENT, filename)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=DIR_CURRENT, suffix='.json.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(document, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, save_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            raise RuntimeError(f"[Outcome] Failed to save {filename}: {e}") from e

    def scan_dates(self) -> Set[str]:
        dates = set()
        if not os.path.exists(DIR_CURRENT): return dates
        pattern = re.compile(r"ledger_(\d{8})\.json")
        for filename in os.listdir(DIR_CURRENT):
            match = pattern.match(filename)
            if match:
                d_str = match.group(1)
                dates.add(f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}")
        return dates
