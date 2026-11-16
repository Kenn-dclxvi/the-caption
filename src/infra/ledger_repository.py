import os
import json
import re
import tempfile
from typing import Optional, Set, Dict, Any, Final, List
from src.config.settings import DIR_CURRENT
from src.lib.logger import setup_logger
from src.lib.models import Ledger
from src.domain.ledger_schema import MonthlyLedger, parse_monthly_ledger, validate_ledger_dict

logger = setup_logger(__name__)

class LedgerRepository:
    __REV: Final[str] = "Rev. 9"

    def __init__(self, current_dir=None) -> None:
        self.current_dir = current_dir
        logger.info(f"[{self.__REV}] Initializing LedgerRepository")

    @property
    def directory(self):
        return self.current_dir or DIR_CURRENT

    def load_for_price_fallback(self, date_str: str) -> Optional[Dict[str, Any]]:
        """A damaged or redirected existing ledger is never treated as absent."""
        path = os.path.join(self.directory, self.__filename_for(date_str))
        if os.path.islink(path):
            raise ValueError("invalid pending calculation ledger path")
        value = self.load(date_str)
        if value is None and os.path.lexists(path):
            raise ValueError("existing ledger is unreadable")
        return value

    def save_for_price_fallback(self, document: Dict[str, Any], date_str: str) -> None:
        self.save_document(document, date_str)
        path = os.path.join(self.directory, self.__filename_for(date_str))
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def __filename_for(self, date_str: str) -> str:
        return f"ledger_{date_str.replace('-', '')}.json"

    def load(self, date_str: str) -> Optional[Dict[str, Any]]:
        filename = self.__filename_for(date_str)
        path = os.path.join(self.directory, filename)
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

    def load_month(self, year_month: str) -> List[MonthlyLedger]:
        # 月次は資産クラス別の推移を出力の正本から組む。ShadowLedger は日次で
        # 上書きされ履歴を残さないため、月の走査対象は ledger_YYYYMMDD.json とする。
        # STAGNANT（暫定）の台帳も対象に含める。ADR-0002 は STAGNANT 中の更新を
        # 許容しており、除外すると月境界の日や月そのものが欠落する。暫定かどうかは
        # integrity_status として domain へ渡し、月次側で可視化する。
        if not os.path.exists(self.directory):
            return []
        prefix = f"ledger_{year_month.replace('-', '')}"
        documents: List[MonthlyLedger] = []
        scanned = 0
        for filename in sorted(os.listdir(self.directory)):
            if not filename.startswith(prefix) or not filename.endswith(".json"):
                continue
            scanned += 1
            path = os.path.join(self.directory, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"[Guard] Skipping unreadable {filename}: {e}")
                continue
            if not validate_ledger_dict(data, source=filename):
                logger.error(f"[Guard] Rejecting {filename}: schema invalid")
                continue
            ledger = parse_monthly_ledger(data, source=filename)
            if ledger is None:
                logger.error(f"[Guard] Rejecting {filename}: monthly schema invalid")
                continue
            documents.append(ledger)
        documents.sort(key=lambda document: document.target_date)
        # 脱落は月境界を黙って別日へずらすため、件数を残す。
        dropped = scanned - len(documents)
        if dropped:
            logger.error(f"[Guard] {dropped}/{scanned} ledgers dropped for {year_month}; month boundary may shift")
        return documents

    def save(self, ledger: Ledger, date_str: str) -> None:
        self.save_document(ledger.to_dict(), date_str)

    def save_document(self, document: Dict[str, Any], date_str: str) -> None:
        filename = self.__filename_for(date_str)
        save_path = os.path.join(self.directory, filename)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self.directory, suffix='.json.tmp')
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
        if not os.path.exists(self.directory): return dates
        pattern = re.compile(r"ledger_(\d{8})\.json")
        for filename in os.listdir(self.directory):
            match = pattern.match(filename)
            if match:
                d_str = match.group(1)
                dates.add(f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}")
        return dates
