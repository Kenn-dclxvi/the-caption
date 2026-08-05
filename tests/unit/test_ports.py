"""domain の port と infra の実装が乖離していないことを確認する。"""

import inspect

from src.domain.ports import LedgerReader
from src.infra.ledger_repository import LedgerRepository


class TestLedgerReader:

    def test_ledger_repository_satisfies_port(self):
        assert isinstance(LedgerRepository(), LedgerReader)

    def test_load_signature_matches_port(self):
        # runtime_checkable はメソッドの存在のみを見るため、引数と戻り値は
        # ここで突き合わせる。port を変えたら実装側も追随させる。
        port_sig = inspect.signature(LedgerReader.load)
        impl_sig = inspect.signature(LedgerRepository.load)

        assert list(port_sig.parameters) == list(impl_sig.parameters)
        assert port_sig.return_annotation == impl_sig.return_annotation
