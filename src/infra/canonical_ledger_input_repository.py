"""Canonical Ledger の計算元入力の読み出し。

検証と正規化は `src.domain.universal_ingester` が持つ。本モジュールは
存在確認と読み出しだけを担い、読めなかった事実は例外のまま返す。
"""

import json
import os
from typing import Any, Optional


class CanonicalLedgerInputRepository:

    def read_external_assets(self, path: str) -> Any:
        # 欠落と不正の区別は呼び出し側が行うため、例外はそのまま送出する。
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_portfolio_basis(self, path: str) -> Optional[Any]:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
