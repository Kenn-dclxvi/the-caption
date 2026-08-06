"""月次が参照する ShadowLedger 履歴の探索と読み出し。

スキーマ検証と対象月の絞り込みは `src.domain.monthly_curator` が持つ。
本モジュールはパス探索と読み出しだけを担う。
"""

import json
import os
from typing import Any, List

from src.config.settings import DATA_DIR


class ShadowLedgerHistoryRepository:

    def discover_shadow_ledger_paths(self) -> List[str]:
        candidates: List[str] = []
        for root, _, files in os.walk(DATA_DIR):
            for filename in files:
                if filename.startswith("v4_shadow_ledger") and filename.endswith(".json"):
                    candidates.append(os.path.join(root, filename))
        return sorted(candidates)

    def read_shadow_ledger(self, path: str) -> Any:
        # 読めなかった事実は例外のまま返す。スキップ判断は呼び出し側が行う。
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
