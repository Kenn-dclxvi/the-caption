"""domain が外部へ要求する境界（port）の定義。

domain は `src/infra` の具象を import せず、必要な操作だけを Protocol として
宣言する。実装は `src/infra` 側が持ち、注入は `src/app` が行う。
"""

from typing import Any, Dict, List, Optional, Protocol, Set, runtime_checkable

import pandas as pd


@runtime_checkable
class LedgerReader(Protocol):
    """確定台帳（出力の正本）の読み出し。実装は `LedgerRepository`。"""

    def load(self, date_str: str) -> Optional[Dict[str, Any]]:
        ...

    def load_month(self, year_month: str) -> List[Dict[str, Any]]:
        """対象月の確定台帳を target_date 昇順で返す。読めない月は空を返す。"""
        ...


@runtime_checkable
class IntelligenceTransporter(Protocol):
    """LLM への問い合わせ。実装は `LlmTransporter`。"""

    def request_intelligence(self, prompt: str) -> str:
        ...


@runtime_checkable
class MarketContextReader(Protocol):
    """市場コンテキストの取得。実装は `MarketDataFetcher`。"""

    def fetch_market_context(self, us_date_str: str) -> str:
        ...


@runtime_checkable
class CanonicalLedgerInputStore(Protocol):
    """Canonical Ledger の計算元入力の読み出しと、統合結果の書き出し。

    実装は `CanonicalLedgerInputRepository`。パスは呼び出し側が保持し、
    本 port はファイルの読み書きだけを担う。検証と正規化は domain 側で行う。
    """

    def read_external_assets(self, path: str) -> Any:
        """SSOT B の payload を返す。読めない場合は例外を送出する。"""
        ...

    def read_portfolio_basis(self, path: str) -> Optional[Any]:
        """portfolio basis の payload を返す。存在しない場合は None を返す。"""
        ...

    def resolve_snapshot_path(self, target_date: str, snapshot_dir: Optional[str]) -> str:
        """日付別 Units snapshot のパスを返す。存在確認は行わない。"""
        ...

    def snapshot_exists(self, path: str) -> bool:
        """snapshot が配置されているかを返す。"""
        ...

    def read_units_snapshot(
        self,
        path: str,
        target_date: str,
        ssot_a_path: str,
    ) -> List[Dict[str, Any]]:
        """snapshot を読み、検証済みの正規化 items を返す。"""
        ...

    def read_market_units_columns(self, csv_path: str) -> Set[str]:
        """SSOT A の列名を返す。行は読まない。"""
        ...

    def read_market_units(self, csv_path: str) -> List[Dict[str, Any]]:
        """SSOT A を読み、正規化済みの行を返す。"""
        ...

    def read_history_frame(
        self,
        history_dir: str,
        asset_name: str,
        date_col: str,
    ) -> Optional[pd.DataFrame]:
        """資産の価格履歴を日付昇順で返す。未配置なら None を返す。"""
        ...

    def write_shadow_ledger(self, path: str, document: Dict[str, Any]) -> None:
        """統合結果を指定パスへ原子的に書き出す。"""
        ...


@runtime_checkable
class MonthlyInsightReader(Protocol):
    """月次 Insight の抽出。実装は `KnowledgeManager`。"""

    def extract_monthly_insights(self, year_month: str) -> List[Dict[str, str]]:
        ...
