"""domain が外部へ要求する境界（port）の定義。

domain は `src/infra` の具象を import せず、必要な操作だけを Protocol として
宣言する。実装は `src/infra` 側が持ち、注入は `src/app` が行う。
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class LedgerReader(Protocol):
    """確定台帳（出力の正本）の読み出し。実装は `LedgerRepository`。"""

    def load(self, date_str: str) -> Optional[Dict[str, Any]]:
        ...
