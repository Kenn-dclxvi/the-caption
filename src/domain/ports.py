"""domain が外部へ要求する境界（port）の定義。

domain は `src/infra` の具象を import せず、必要な操作だけを Protocol として
宣言する。実装は `src/infra` 側が持ち、注入は `src/app` が行う。
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LedgerReader(Protocol):
    """確定台帳（出力の正本）の読み出し。実装は `LedgerRepository`。"""

    def load(self, date_str: str) -> Optional[Dict[str, Any]]:
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
    """Canonical Ledger の計算元入力の読み出し。

    実装は `CanonicalLedgerInputRepository`。パスは呼び出し側が保持し、
    本 port は読み出しだけを担う。検証と正規化は domain 側で行う。
    """

    def read_external_assets(self, path: str) -> Any:
        """SSOT B の payload を返す。読めない場合は例外を送出する。"""
        ...

    def read_portfolio_basis(self, path: str) -> Optional[Any]:
        """portfolio basis の payload を返す。存在しない場合は None を返す。"""
        ...


@runtime_checkable
class MonthlyInsightReader(Protocol):
    """月次 Insight の抽出。実装は `KnowledgeManager`。"""

    def extract_monthly_insights(self, year_month: str) -> List[Dict[str, str]]:
        ...
