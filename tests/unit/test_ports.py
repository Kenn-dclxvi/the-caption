"""domain の port と infra の実装が乖離していないことを確認する。"""

import inspect

import pytest

from src.domain.ports import (
    CanonicalLedgerInputStore,
    IntelligenceTransporter,
    LedgerReader,
    MarketContextReader,
    MonthlyInsightReader,
)
from src.infra.canonical_ledger_input_repository import CanonicalLedgerInputRepository
from src.infra.knowledge_manager import KnowledgeManager
from src.infra.ledger_repository import LedgerRepository
from src.infra.llm_transporter import LlmTransporter
from src.infra.market_data import MarketDataFetcher

# port と、それを満たすべき infra 実装、突き合わせる操作名。
_PORT_IMPLEMENTATIONS = [
    (LedgerReader, LedgerRepository, "load"),
    (LedgerReader, LedgerRepository, "load_month"),
    (IntelligenceTransporter, LlmTransporter, "request_intelligence"),
    (MarketContextReader, MarketDataFetcher, "fetch_market_context"),
    (MonthlyInsightReader, KnowledgeManager, "extract_monthly_insights"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "read_external_assets"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "read_portfolio_basis"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "resolve_snapshot_path"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "snapshot_exists"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "read_units_snapshot"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "read_market_units_columns"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "read_market_units"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "read_history_frame"),
    (CanonicalLedgerInputStore, CanonicalLedgerInputRepository, "write_shadow_ledger"),
]


@pytest.mark.parametrize("port, impl, method", _PORT_IMPLEMENTATIONS)
class TestPortImplementations:

    def test_impl_exposes_port_method(self, port, impl, method):
        assert callable(getattr(impl, method, None))

    def test_signature_matches_port(self, port, impl, method):
        # runtime_checkable はメソッドの存在のみを見るため、引数と戻り値は
        # ここで突き合わせる。port を変えたら実装側も追随させる。
        # 実装のインスタンス化は副作用を伴うため、クラス経由で比較する。
        port_sig = inspect.signature(getattr(port, method))
        impl_sig = inspect.signature(getattr(impl, method))

        assert list(port_sig.parameters) == list(impl_sig.parameters)
        assert port_sig.return_annotation == impl_sig.return_annotation


class TestLedgerReader:

    def test_ledger_repository_satisfies_port(self):
        # LedgerRepository は生成が logger のみで副作用がないため実体で確認する。
        assert isinstance(LedgerRepository(), LedgerReader)
