"""保存済みの確定台帳（出力の正本）に対する回帰検証。

`data/` は .gitignore 済みのため、CI ではパラメータが空になりローカル専用の
検証として機能する。

以前は「月初・週初の台帳では MTD / WTD が DAY と一致する」ことで期間騰落の
リセットを検証していた。しかし DAY の基準を前営業日の確定台帳（円建て評価額の
変化）へ移した一方、期間騰落は取得元履歴の期間起点基準のままであり
（ADR-0002 の Open items）、同じ起点でも両者は一致しない。期間起点の解決と
合計の加重方式そのものは、固定データを使う
`tests/unit/test_universal_ingester.py` と
`tests/unit/test_shadow_ledger_adapter.py` が検証している。

ここでは基準の違いに影響されない、正本自体の整合を検証する。
期間騰落が正本基準へ移行した際は、リセットの検証を再度追加する。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "current"
_LEDGER_RE = re.compile(r"ledger_(\d{8})\.json$")


def _ledger_dates() -> List[str]:
    dates = []
    for path in sorted(DATA_DIR.glob("ledger_*.json")):
        match = _LEDGER_RE.match(path.name)
        if match:
            digits = match.group(1)
            dates.append(f"{digits[:4]}-{digits[4:6]}-{digits[6:]}")
    return dates


def _load(date_str: str) -> Dict[str, Any]:
    return json.loads((DATA_DIR / f"ledger_{date_str.replace('-', '')}.json").read_text(encoding="utf-8"))


def _is_v4(ledger: Dict[str, Any]) -> bool:
    return "-v4" in str(ledger.get("meta", {}).get("version", ""))


def _v4_ledger_dates() -> List[str]:
    return [d for d in _ledger_dates() if _is_v4(_load(d))]


@pytest.mark.parametrize("date_str", _ledger_dates())
def test_class_totals_match_the_recorded_total(date_str: str) -> None:
    summary = _load(date_str)["summary"]
    assert sum(summary.get("class_totals", {}).values()) == summary["total_assets_jpy"]


@pytest.mark.parametrize("date_str", _ledger_dates())
def test_integrity_status_is_a_known_state(date_str: str) -> None:
    assert _load(date_str)["meta"]["integrity_status"] in ("VERIFIED", "STAGNANT")


@pytest.mark.parametrize("date_str", _ledger_dates())
def test_target_date_matches_the_filename(date_str: str) -> None:
    assert _load(date_str)["meta"]["target_date"] == date_str


@pytest.mark.parametrize("date_str", _v4_ledger_dates())
def test_exposure_and_iron_bank_account_for_the_total(date_str: str) -> None:
    # v3.5 以前の台帳は summary の定義が異なるため v4 の正本のみを対象とする。
    summary = _load(date_str)["summary"]
    assert summary["exposure_jpy"] + summary["iron_bank_jpy"] == summary["total_assets_jpy"]


@pytest.mark.parametrize("date_str", _v4_ledger_dates())
def test_asset_values_account_for_the_total(date_str: str) -> None:
    ledger = _load(date_str)
    assert sum(a["value_jpy"] for a in ledger["assets"]) == ledger["summary"]["total_assets_jpy"]


@pytest.mark.parametrize("date_str", _v4_ledger_dates())
def test_verified_ledgers_have_no_unconfirmed_asset(date_str: str) -> None:
    # VERIFIED は全資産が確定していることを表す（ADR-0002）。
    ledger = _load(date_str)
    if ledger["meta"]["integrity_status"] != "VERIFIED":
        pytest.skip("provisional ledger")
    unconfirmed = [a["name"] for a in ledger["assets"] if a.get("pricing_status") not in ("PRICED", "STATIC")]
    assert unconfirmed == []


@pytest.mark.parametrize("date_str", _v4_ledger_dates())
def test_market_assets_record_their_pricing_provenance(date_str: str) -> None:
    # 正本は「いつの価格をどの状態で採用したか」を資産別に保持する。
    for asset in _load(date_str)["assets"]:
        if asset.get("source") != "MARKET_UNITS":
            continue
        assert asset.get("pricing_status"), f"{asset['name']} has no pricing_status"
        if asset["pricing_status"] != "MISSING":
            assert asset.get("source_date"), f"{asset['name']} has no source_date"
            assert isinstance(asset.get("price"), (int, float)), f"{asset['name']} has no price"


@pytest.mark.parametrize("date_str", _v4_ledger_dates())
def test_v4_ledgers_do_not_carry_per_asset_acquisition_cost(date_str: str) -> None:
    # v4 の計算元に資産別取得原価は存在しないため、ダミー値を持たせない（ADR-0002）。
    for asset in _load(date_str)["assets"]:
        assert "acquisition_price" not in asset
        assert "profit_loss" not in asset
