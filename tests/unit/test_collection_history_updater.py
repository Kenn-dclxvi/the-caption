import os
from unittest.mock import MagicMock, patch

import pandas as pd

from src.infra.collection_history_updater import CollectionHistoryUpdater


def _make_updater(tmp_path, asset_class="ETF"):
    funds_csv = tmp_path / "funds.csv"
    funds_csv.write_text(
        f"name,asset_class,source_symbol,csv_url\nSPY,{asset_class},SPY,\n",
        encoding="utf-8",
    )
    return CollectionHistoryUpdater(
        funds_csv_path=str(funds_csv),
        history_dir=str(tmp_path / "history"),
    )


def _dummy_df():
    return pd.DataFrame({"Close": [100.0]}, index=pd.to_datetime(["2026-05-19"]))


def _missing_expected_close_df():
    return pd.DataFrame(
        {"Close": [100.0, float("nan")]},
        index=pd.to_datetime(["2026-05-20", "2026-05-21"]),
    )


def _missing_close_column_df():
    return pd.DataFrame(
        {"Open": [100.0]},
        index=pd.to_datetime(["2026-05-21"]),
    )


def _empty_close_dataframe_df():
    return pd.DataFrame(
        {("Close", "SPY"): []},
        index=pd.to_datetime([]),
    )


def _mock_alpha_vantage_response(close="123.45"):
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = (
        b'{"Time Series (Daily)": {"2026-05-21": {"4. close": "' + close.encode("utf-8") + b'"}}}'
    )
    return resp


def test_refresh_with_end_date_passes_end_to_yf_download(tmp_path):
    # yfinance の end は exclusive のため trading_date+1日が渡されることを確認
    updater = _make_updater(tmp_path)
    with patch("src.infra.collection_history_updater.yf.download", return_value=_dummy_df()) as mock_dl:
        updater.refresh(end_date="2026-05-19")
    mock_dl.assert_called_once()
    _, kwargs = mock_dl.call_args
    assert kwargs.get("end") == "2026-05-20"  # 2026-05-19 + 1日


def test_refresh_without_end_date_omits_end_from_yf_download(tmp_path):
    updater = _make_updater(tmp_path)
    with patch("src.infra.collection_history_updater.yf.download", return_value=_dummy_df()) as mock_dl:
        updater.refresh()
    mock_dl.assert_called_once()
    _, kwargs = mock_dl.call_args
    assert "end" not in kwargs


def test_refresh_uses_target_date_for_jp_stock(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    funds_csv.write_text(
        "name,asset_class,source_symbol,csv_url\nBestAI,JP_STOCK,408A.T,\n",
        encoding="utf-8",
    )
    updater = CollectionHistoryUpdater(
        funds_csv_path=str(funds_csv),
        history_dir=str(tmp_path / "history"),
    )
    with patch("src.infra.collection_history_updater.yf.download", return_value=_dummy_df()) as mock_dl:
        updater.refresh(target_date="2026-05-22", us_market_date="2026-05-21")
    _, kwargs = mock_dl.call_args
    assert kwargs.get("end") == "2026-05-23"


def test_refresh_uses_us_market_date_for_us_stock(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    funds_csv.write_text(
        "name,asset_class,source_symbol,csv_url\nTSMC,US_STOCK,TSM,\n",
        encoding="utf-8",
    )
    updater = CollectionHistoryUpdater(
        funds_csv_path=str(funds_csv),
        history_dir=str(tmp_path / "history"),
    )
    with (
        patch("src.infra.collection_history_updater.os.getenv", return_value=None),
        patch("src.infra.collection_history_updater.yf.download", return_value=_dummy_df()) as mock_dl,
    ):
        updater.refresh(target_date="2026-05-22", us_market_date="2026-05-21")
    _, kwargs = mock_dl.call_args
    assert kwargs.get("end") == "2026-05-22"


def test_selective_refresh_includes_fx_dependency_for_us_stock(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    funds_csv.write_text(
        "\n".join([
            "name,asset_class,source_symbol,csv_url",
            "TSMC,US_STOCK,TSM,",
            "USDJPY,FX,JPY=X,",
        ]) + "\n",
        encoding="utf-8",
    )
    updater = CollectionHistoryUpdater(
        funds_csv_path=str(funds_csv),
        history_dir=str(tmp_path / "history"),
    )
    with (
        patch("src.infra.collection_history_updater.os.getenv", return_value=None),
        patch("src.infra.collection_history_updater.yf.download", return_value=_dummy_df()) as mock_dl,
    ):
        updater.refresh(
            target_date="2026-05-22",
            us_market_date="2026-05-21",
            only_assets={"TSMC"},
        )

    assert mock_dl.call_count == 2
    first_args, first_kwargs = mock_dl.call_args_list[0]
    second_args, second_kwargs = mock_dl.call_args_list[1]
    assert {first_args[0], second_args[0]} == {"TSM", "JPY=X"}
    assert first_kwargs.get("end") == "2026-05-22"
    assert second_kwargs.get("end") == "2026-05-22"


def test_load_fund_config_defaults_blank_optional_fields(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    funds_csv.write_text(
        "name,asset_class,source_symbol,csv_url\n"
        "Alpha,,,https://example.test/nav.csv\n",
        encoding="utf-8",
    )

    updater = CollectionHistoryUpdater(funds_csv_path=str(funds_csv), history_dir=str(tmp_path / "history"))
    assets = updater._load_fund_config()

    assert len(assets) == 1
    assert assets[0]["name"] == "Alpha"
    assert assets[0]["asset_class"] == "MUTUAL_FUNDS"
    assert assets[0]["source_symbol"] == "Alpha"
    assert assets[0]["csv_url"] == "https://example.test/nav.csv"


def test_us_stock_missing_expected_close_uses_alpha_vantage_fallback(tmp_path):
    updater = _make_updater(tmp_path, asset_class="US_STOCK")
    with (
        patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}),
        patch("src.infra.collection_history_updater.yf.download", return_value=_missing_expected_close_df()),
        patch(
            "src.infra.collection_history_updater.urllib.request.urlopen",
            return_value=_mock_alpha_vantage_response("123.45"),
        ) as mock_urlopen,
    ):
        updater.refresh(end_date="2026-05-21")

    mock_urlopen.assert_called_once()
    hist = pd.read_csv(tmp_path / "history" / "SPY.csv", parse_dates=["Date"])
    expected = hist[hist["Date"] == pd.Timestamp("2026-05-21")]
    assert expected["Close"].tolist() == [123.45]


def test_us_stock_empty_yfinance_result_uses_alpha_vantage_fallback(tmp_path):
    updater = _make_updater(tmp_path, asset_class="US_STOCK")
    with (
        patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}),
        patch("src.infra.collection_history_updater.yf.download", return_value=pd.DataFrame()),
        patch(
            "src.infra.collection_history_updater.urllib.request.urlopen",
            return_value=_mock_alpha_vantage_response("123.45"),
        ) as mock_urlopen,
    ):
        updater.refresh(end_date="2026-05-21")

    mock_urlopen.assert_called_once()
    hist = pd.read_csv(tmp_path / "history" / "SPY.csv", parse_dates=["Date"])
    assert hist["Date"].tolist() == [pd.Timestamp("2026-05-21")]
    assert hist["Close"].tolist() == [123.45]


def test_us_stock_missing_close_column_uses_alpha_vantage_fallback(tmp_path):
    updater = _make_updater(tmp_path, asset_class="US_STOCK")
    with (
        patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}),
        patch("src.infra.collection_history_updater.yf.download", return_value=_missing_close_column_df()),
        patch(
            "src.infra.collection_history_updater.urllib.request.urlopen",
            return_value=_mock_alpha_vantage_response("123.45"),
        ) as mock_urlopen,
    ):
        updater.refresh(end_date="2026-05-21")

    mock_urlopen.assert_called_once()
    hist = pd.read_csv(tmp_path / "history" / "SPY.csv", parse_dates=["Date"])
    assert hist["Date"].tolist() == [pd.Timestamp("2026-05-21")]
    assert hist["Close"].tolist() == [123.45]


def test_us_stock_empty_close_dataframe_uses_alpha_vantage_fallback(tmp_path):
    updater = _make_updater(tmp_path, asset_class="US_STOCK")
    with (
        patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}),
        patch("src.infra.collection_history_updater.yf.download", return_value=_empty_close_dataframe_df()),
        patch(
            "src.infra.collection_history_updater.urllib.request.urlopen",
            return_value=_mock_alpha_vantage_response("123.45"),
        ) as mock_urlopen,
    ):
        updater.refresh(end_date="2026-05-21")

    mock_urlopen.assert_called_once()
    hist = pd.read_csv(tmp_path / "history" / "SPY.csv", parse_dates=["Date"])
    assert hist["Date"].tolist() == [pd.Timestamp("2026-05-21")]
    assert hist["Close"].tolist() == [123.45]


def test_us_stock_missing_expected_close_without_alpha_key_does_not_fallback(tmp_path):
    updater = _make_updater(tmp_path, asset_class="US_STOCK")
    with (
        patch.dict(os.environ, {}, clear=True),
        patch("src.infra.collection_history_updater.yf.download", return_value=_missing_expected_close_df()),
        patch("src.infra.collection_history_updater.urllib.request.urlopen") as mock_urlopen,
    ):
        updater.refresh(end_date="2026-05-21")

    mock_urlopen.assert_not_called()
    hist = pd.read_csv(tmp_path / "history" / "SPY.csv", parse_dates=["Date"])
    assert pd.Timestamp("2026-05-21") not in set(hist["Date"])


def test_non_us_stock_missing_expected_close_does_not_use_alpha_vantage_fallback(tmp_path):
    updater = _make_updater(tmp_path, asset_class="JP_STOCK")
    with (
        patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}),
        patch("src.infra.collection_history_updater.yf.download", return_value=_missing_expected_close_df()),
        patch("src.infra.collection_history_updater.urllib.request.urlopen") as mock_urlopen,
    ):
        updater.refresh(end_date="2026-05-21")

    mock_urlopen.assert_not_called()
    hist = pd.read_csv(tmp_path / "history" / "SPY.csv", parse_dates=["Date"])
    assert pd.Timestamp("2026-05-21") not in set(hist["Date"])
