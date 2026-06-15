from typing import Any, Final

from src.domain.ledger_schema import ShadowLedger

SCHEMA_VERSION: Final[str] = "v4.1-daily-metrics"


def build_daily_metrics(shadow_ledger: ShadowLedger) -> dict[str, Any]:
    market_assets = [asset for asset in shadow_ledger.assets if asset.source == "MARKET_UNITS"]
    absolute_assets = [asset for asset in shadow_ledger.assets if asset.source == "ABSOLUTE_AMOUNT"]
    missing_assets = [asset for asset in shadow_ledger.assets if asset.pricing_status == "MISSING"]
    stale_assets = [asset for asset in shadow_ledger.assets if asset.pricing_status == "STALE"]

    total_value = shadow_ledger.total_value_jpy
    return {
        "schema_version": SCHEMA_VERSION,
        "target_date": shadow_ledger.target_date,
        "total_value_jpy": total_value,
        "market_units_value_jpy": sum(asset.current_value_jpy for asset in market_assets),
        "absolute_amount_value_jpy": sum(asset.current_value_jpy for asset in absolute_assets),
        "return_base_value_jpy": shadow_ledger.return_base_value_jpy,
        "total_acquisition_cost_jpy": shadow_ledger.total_acquisition_cost_jpy,
        "total_return_jpy": shadow_ledger.total_return_jpy,
        "total_return_pct": shadow_ledger.total_return_pct,
        "pricing_missing_count": len(missing_assets),
        "pricing_stale_count": len(stale_assets),
        "asset_count": len(shadow_ledger.assets),
        "market_units_count": len(market_assets),
        "absolute_amount_count": len(absolute_assets),
        "top_movers": _build_top_movers(shadow_ledger),
        "data_quality": {
            "has_assets": len(shadow_ledger.assets) > 0,
            "has_positive_total": total_value > 0,
            "has_missing_pricing": len(missing_assets) > 0,
            "has_stale_pricing": len(stale_assets) > 0,
        },
    }


def build_deterministic_daily_context(
    shadow_ledger: ShadowLedger,
    metrics: dict[str, Any],
    market_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    label = _classify_state(metrics)
    missing_count = metrics.get("pricing_missing_count", 0)
    stale_count = metrics.get("pricing_stale_count", 0)
    market_summary = (market_context or {}).get("market_summary", "")
    primary = _primary_force(metrics)
    note = "日次AI鑑定は月次集約へ移行中です。日次は台帳と市場観測値の保存を優先します。"
    if missing_count:
        note = f"価格未着が{missing_count}件あります。月次集約では欠損日として扱います。"
    elif stale_count:
        note = f"価格基準日未達の資産が{stale_count}件あります。最新データ取得後に再送信します。"

    return {
        "display_context": {
            "state": label,
            "primary": primary,
            "policy": "月次監査へ集約",
            "shield": "月次評価へ集約",
        },
        "archive_context": {
            "causal_vector": "UNKNOWN",
            "market_regime": "UNKNOWN",
            "fx_effect": "UNKNOWN",
            "vix_band": "UNKNOWN",
            "monthly_tags": ["DAILY_METRICS_ONLY"],
            "short_note": note,
        },
        "state_classification": {
            "label": label,
            "summary": note,
            "primary_force": primary,
            "action_posture": "追加判断は保留" if (missing_count or stale_count) else "行動なし",
        },
        "portfolio_audit": {
            "core_thesis": "方針維持",
            "cash_buffer": "適正",
            "stagnation_readiness": "中",
            "commentary": "日次の方針監査は月次へ集約します。本日は確定的な台帳記録のみを保存しています。",
        },
        "insight": {
            "theme": "日次記録",
            "analysis": "AIによる日次因果鑑定は通常経路では実行しません。月次で台帳推移と構造化メトリクスを統合します。",
            "vix_vector": market_summary or "市場スナップショット未取得",
        },
        "shield_evaluation": {
            "status": "中立",
            "commentary": "防壁評価は月次Shield評価へ集約します。",
        },
        "market_context": market_context or {},
        "daily_metrics": metrics,
    }


def _build_top_movers(shadow_ledger: ShadowLedger, limit: int = 5) -> list[dict[str, Any]]:
    movable_assets = [
        asset
        for asset in shadow_ledger.assets
        if asset.diff_val_jpy is not None
    ]
    ranked_assets = sorted(
        movable_assets,
        key=lambda asset: abs(asset.diff_val_jpy or 0),
        reverse=True,
    )
    return [
        {
            "name": asset.name,
            "source": asset.source,
            "asset_class": asset.asset_class,
            "current_value_jpy": asset.current_value_jpy,
            "diff_val_jpy": asset.diff_val_jpy,
            "diff_pct": asset.diff_pct,
            "pricing_status": asset.pricing_status,
        }
        for asset in ranked_assets[:limit]
    ]


def _classify_state(metrics: dict[str, Any]) -> str:
    if metrics.get("pricing_missing_count", 0) > 0 or metrics.get("pricing_stale_count", 0) > 0:
        return "WATCH"
    total_value = metrics.get("total_value_jpy", 0)
    if not total_value:
        return "BREAK"
    return "NORMAL"


def _primary_force(metrics: dict[str, Any]) -> str:
    movers = metrics.get("top_movers") or []
    if not movers:
        return "No priced movers"
    lead = movers[0]
    diff = lead.get("diff_val_jpy")
    if diff is None:
        return str(lead.get("name", "UNKNOWN"))
    return f"{lead.get('name', 'UNKNOWN')} / {diff:+,.0f} JPY"
