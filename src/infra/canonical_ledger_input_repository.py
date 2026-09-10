"""Canonical Ledger の計算元入力の読み出し。

検証と正規化は `src.domain.universal_ingester` と
`src.domain.market_units_snapshot` が持つ。本モジュールは存在確認と
読み出しだけを担い、読めなかった事実は例外のまま返す。
"""

import csv
import io
import os
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from src.infra.market_units_snapshot_repository import (
    load_market_units_csv,
    load_units_snapshot,
    snapshot_path,
)
from src.infra.market_units_input_repository import locked_market_units_csv
from src.lib.atomic_write import atomic_write_json
from src.infra.monthly_input_repository import MonthlyInputRepository


class CanonicalLedgerInputRepository:

    def read_external_assets(self, path: str) -> Any:
        # 欠落と不正の区別は呼び出し側が行うため、例外はそのまま送出する。
        value = MonthlyInputRepository(path, "external-assets").read_legacy()
        if value is None:
            raise FileNotFoundError(path)
        return value

    def read_portfolio_basis(self, path: str) -> Optional[Any]:
        return MonthlyInputRepository(path, "portfolio-basis").read_legacy()

    def resolve_snapshot_path(self, target_date: str, snapshot_dir: Optional[str]) -> str:
        return snapshot_path(target_date, snapshot_dir)

    def snapshot_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def read_units_snapshot(
        self,
        path: str,
        target_date: str,
        ssot_a_path: str,
    ) -> List[Dict[str, Any]]:
        return load_units_snapshot(path, target_date, ssot_a_path)

    def read_market_units_columns(self, csv_path: str) -> Set[str]:
        with locked_market_units_csv(csv_path) as raw_csv:
            reader = csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig"), newline=""))
            return set(reader.fieldnames or [])

    def read_market_units(self, csv_path: str) -> List[Dict[str, Any]]:
        return load_market_units_csv(csv_path)

    def read_history_frame(
        self,
        history_dir: str,
        asset_name: str,
        date_col: str,
    ) -> Optional[pd.DataFrame]:
        # 読めなかった事実は例外のまま返す。警告の出し方は呼び出し側が決める。
        hist_path = os.path.join(history_dir, f"{asset_name}.csv")
        if not os.path.exists(hist_path):
            return None
        df = pd.read_csv(hist_path, parse_dates=[date_col])
        return df.sort_values(date_col).reset_index(drop=True)

    def write_shadow_ledger(self, path: str, document: Dict[str, Any]) -> None:
        atomic_write_json(path, document)
