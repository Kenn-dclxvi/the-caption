from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Final, List, Optional

from src.domain.ledger_schema import ShadowLedger
from src.app.renderer.view_models import PositionViewModel, SummaryViewModel
from src.config.settings import VERSION

_C_GOLD: Final[str] = "#c5a059"
_C_INK: Final[str] = "#1e293b"
_C_SLATE: Final[str] = "#64748b"
_MARKET_CONTEXT_ORDER: Final[tuple[str, ...]] = (
    "S&P500",
    "NASDAQ100",
    "SOX",
    "米10年債",
    "USD/JPY",
    "VIX",
)


@dataclass(frozen=True)
class V4LedgerRowViewModel:
    name: str
    asset_class: str
    source: str
    fmt_value: str
    share_pct: float
    metric_capsule: str
    value_color: str
    fmt_day: str = "---"
    fmt_mtd: str = "---"
    fmt_ytd: str = "---"
    fmt_wtd: str = "---"
    fmt_units: str = ""
    fmt_price: str = ""
    day_color: str = _C_INK
    metrics_display_style: str = "display: block;"
    day_detail_line: str = ""


class V4MonolithicViewModel:
    def __init__(
        self,
        shadow_ledger: ShadowLedger,
        context_data: Dict[str, Any],
        summary_vm: Optional[SummaryViewModel] = None,
        asset_vms: Optional[List[PositionViewModel]] = None,
    ) -> None:
        self.__ledger = shadow_ledger
        self.__context = context_data or {}
        self.__summary_vm = summary_vm
        self.__asset_vm_map = self.__build_asset_vm_map(asset_vms or [])
        self.__rows = self.__build_rows()
        self.__iron_bank_rows = self.__build_rows(include_static=True)

    @property
    def target_date(self) -> str:
        return self.__ledger.target_date

    @property
    def theme_title(self) -> str:
        return "DAILY PORTFOLIO APPRAISAL"

    @property
    def theme_subtitle(self) -> str:
        insight = self.__insight
        return str(
            insight.get("theme")
            or self.__context.get("theme")
            or self.__context.get("theme_title")
            or ""
        )

    @property
    def show_appraisal(self) -> bool:
        visibility = self.__context.get("appraisal_visibility")
        if isinstance(visibility, dict) and "show" in visibility:
            return bool(visibility.get("show"))
        return True

    @property
    def market_context(self) -> str:
        meta = self.__context.get("meta") if isinstance(self.__context.get("meta"), dict) else {}
        market_context = self.__context.get("market_context")
        if isinstance(market_context, dict) and market_context.get("market_summary"):
            return str(market_context.get("market_summary"))
        theme_code = meta.get("theme_code", "N/A")
        priced = sum(1 for asset in self.__ledger.assets if asset.pricing_status == "PRICED")
        static = sum(1 for asset in self.__ledger.assets if asset.pricing_status == "STATIC")
        missing = sum(1 for asset in self.__ledger.assets if asset.pricing_status == "MISSING")
        return f"{theme_code} / PRICED {priced} / STATIC {static} / MISSING {missing}"

    @property
    def market_context_metrics(self) -> List[Dict[str, str]]:
        raw = self.market_context
        parts = [part.strip() for part in raw.split("|") if part.strip()]
        metrics: List[Dict[str, str]] = []
        for part in parts:
            if ":" in part:
                label, value = part.split(":", 1)
                metrics.append({"label": label.strip(), "value": value.strip()})
            else:
                metrics.append({"label": "MARKET", "value": part})
        if not metrics:
            return [{"label": "MARKET", "value": "---"}]
        index_map = {label: i for i, label in enumerate(_MARKET_CONTEXT_ORDER)}
        return sorted(
            metrics,
            key=lambda metric: (index_map.get(metric["label"], len(index_map)), metric["label"]),
        )

    @property
    def state_label(self) -> str:
        state = self.__state_classification
        return str(state.get("label") or self.__computed_state_label)

    @property
    def state_summary(self) -> str:
        state = self.__state_classification
        return str(state.get("summary") or self.__computed_state_summary)

    @property
    def primary_force(self) -> str:
        state = self.__state_classification
        return str(state.get("primary_force") or self.__computed_primary_force)

    @property
    def action_posture(self) -> str:
        state = self.__state_classification
        if state.get("action_posture"):
            return str(state.get("action_posture"))
        return self.__action_posture_for(self.state_label)

    @property
    def display_context(self) -> Dict[str, Any]:
        existing = self.__context.get("display_context")
        if isinstance(existing, dict):
            return existing
        return {
            "state": self.state_label,
            "primary": self.primary_force,
            "policy": self.portfolio_audit_status,
            "shield": self.shield_status,
            "safe_ratio": self.fmt_safe_ratio,
            "total_net_assets": self.fmt_total_net_assets,
            "day": f"{self.fmt_total_day} / {self.fmt_total_day_pct}",
        }

    @property
    def archive_context(self) -> Dict[str, Any]:
        existing = self.__context.get("archive_context")
        if isinstance(existing, dict):
            return existing
        return {
            "state": self.state_label,
            "primary_asset": self.__top_impact_row.name if self.__top_impact_row else "",
            "primary_impact_pt": round(self.__top_impact_signed_score, 2),
            "causal_vector": str(self.__context.get("causality_vector") or "UNKNOWN"),
            "market_regime": self.__market_regime,
            "fx_effect": self.__fx_effect,
            "vix_band": self.__vix_band,
            "policy_status": self.portfolio_audit_status,
            "shield_status": self.shield_status,
            "monthly_tags": self.__monthly_tags,
            "short_note": self.__archive_short_note,
        }

    @property
    def portfolio_audit_status(self) -> str:
        audit = self.__portfolio_audit
        if not audit:
            return "UNKNOWN"
        parts = [
            str(audit.get("core_thesis") or "").strip(),
            str(audit.get("cash_buffer") or "").strip(),
            str(audit.get("stagnation_readiness") or "").strip(),
        ]
        return " / ".join(part for part in parts if part) or "UNKNOWN"

    @property
    def portfolio_audit_summary(self) -> str:
        audit = self.__portfolio_audit
        return str(audit.get("commentary") or audit.get("summary") or "") if audit else ""

    @property
    def fmt_total_net_assets(self) -> str:
        return f"{int(round(self.__ledger.total_value_jpy)):,}"

    @property
    def total_return_anchor(self) -> str:
        if self.__ledger.total_return_jpy is None:
            return "---"
        if self.__summary_vm:
            return self.__summary_vm.fmt_total_pl
        meta = self.__context.get("meta") if isinstance(self.__context.get("meta"), dict) else {}
        return str(meta.get("total_return") or "---")

    @property
    def ytd_anchor(self) -> str:
        return self.__summary_vm.total_ytd if self.__summary_vm else "---"

    @property
    def fmt_safe_ratio(self) -> str:
        return self.__summary_vm.fmt_safe_ratio if self.__summary_vm else "---"

    @property
    def fmt_exposure(self) -> str:
        return self.__summary_vm.fmt_exposure if self.__summary_vm else "---"

    @property
    def fmt_iron_bank(self) -> str:
        return self.__summary_vm.fmt_iron_bank if self.__summary_vm else "---"

    @property
    def fmt_total_day(self) -> str:
        return self.__summary_vm.fmt_total_diff if self.__summary_vm else "---"

    @property
    def fmt_total_day_pct(self) -> str:
        return self.__summary_vm.fmt_total_diff_pct if self.__summary_vm else "---"

    @property
    def day_color(self) -> str:
        return self.__summary_vm.day_color if self.__summary_vm else _C_INK

    @property
    def total_mtd(self) -> str:
        return self.__summary_vm.total_mtd if self.__summary_vm else "---"

    @property
    def total_wtd(self) -> str:
        return self.__summary_vm.total_wtd if self.__summary_vm else "---"

    @property
    def exposure_width_pct(self) -> float:
        return self.__summary_vm.exposure_width_pct if self.__summary_vm else 0.0

    @property
    def slate_share(self) -> float:
        return self.__summary_vm.slate_share if self.__summary_vm else 100.0

    @property
    def gold_share(self) -> float:
        return self.__summary_vm.gold_share if self.__summary_vm else 0.0

    @property
    def safe_ratio_pct(self) -> float:
        return self.__summary_vm.safe_ratio_pct if self.__summary_vm else 0.0

    @property
    def total_pl_color(self) -> str:
        return self.__summary_vm.total_pl_color if self.__summary_vm else _C_INK

    @property
    def insight_body(self) -> str:
        insight = self.__insight
        if insight:
            parts = [str(insight.get("analysis") or "")]
            if insight.get("vix_vector"):
                parts.append(str(insight.get("vix_vector")))
            return "\n\n".join(part for part in parts if part)
        return str(
            self.__context.get("overview")
            or self.__context.get("implication")
            or self.__context.get("insight")
            or ""
        )

    @property
    def ledger_rows(self) -> List[V4LedgerRowViewModel]:
        return self.__rows

    @property
    def exposure_rows(self) -> List[V4LedgerRowViewModel]:
        return self.__rows

    @property
    def iron_bank_rows(self) -> List[V4LedgerRowViewModel]:
        return self.__iron_bank_rows

    @property
    def fmt_iron_bank_static_total(self) -> str:
        total = sum(self.__row_value(row) for row in self.__iron_bank_rows)
        return f"{total:,}"

    @property
    def shield_evaluation(self) -> str:
        shield = self.__context.get("shield_evaluation")
        if isinstance(shield, dict):
            status = str(shield.get("status") or "").strip()
            commentary = str(shield.get("commentary") or "").strip()
            return " / ".join(part for part in [status, commentary] if part)
        return str(shield or "No shield evaluation available.")

    @property
    def shield_status(self) -> str:
        shield = self.__context.get("shield_evaluation")
        if isinstance(shield, dict):
            return str(shield.get("status") or "UNKNOWN").strip() or "UNKNOWN"
        raw = str(shield or "").strip()
        return raw.split("/", 1)[0].strip() if raw else "UNKNOWN"

    @property
    def footer_label(self) -> str:
        return f"THE CAPTION {VERSION}"

    @property
    def __state_classification(self) -> Dict[str, Any]:
        state = self.__context.get("state_classification")
        return state if isinstance(state, dict) else {}

    @property
    def __portfolio_audit(self) -> Dict[str, Any]:
        audit = self.__context.get("portfolio_audit")
        return audit if isinstance(audit, dict) else {}

    @property
    def __insight(self) -> Dict[str, Any]:
        insight = self.__context.get("insight")
        return insight if isinstance(insight, dict) else {}

    def __build_asset_vm_map(self, asset_vms: List[PositionViewModel]) -> Dict[str, PositionViewModel]:
        result: Dict[str, PositionViewModel] = {}
        for vm in asset_vms:
            result[vm.id] = vm
            result[vm.name] = vm
        return result

    def __build_rows(self, include_static: bool = False) -> List[V4LedgerRowViewModel]:
        assets = [
            asset for asset in self.__ledger.assets
            if self.__is_static_external(asset) is include_static
        ]
        total = sum(asset.current_value_jpy for asset in assets)
        rows: List[V4LedgerRowViewModel] = []
        for asset in sorted(assets, key=lambda item: item.current_value_jpy, reverse=True):
            share = (asset.current_value_jpy / total * 100.0) if total > 0 else 0.0
            value = int(round(asset.current_value_jpy))
            metric_vm = self.__asset_vm_map.get(asset.source_symbol or "") or self.__asset_vm_map.get(asset.name)
            is_static_external = self.__is_static_external(asset)
            fmt_units = ""
            fmt_price = ""
            capsule_parts: List[str] = []
            if not is_static_external and asset.units is not None:
                fmt_units = self.__fmt_units(asset.units)
                capsule_parts.append(f"UNITS {fmt_units}")
            if not is_static_external and asset.price is not None:
                fmt_price = self.__fmt_price(asset.price)
                capsule_parts.append(f"PRICE {fmt_price}")
            fmt_day = self.__fmt_day_value(asset.diff_val_jpy, metric_vm)
            fmt_day_pct = self.__fmt_pct(asset.diff_pct, metric_vm.fmt_diff_pct if metric_vm else None)
            fmt_day_pct = f"{fmt_day_pct}{self.__source_date_note(asset)}"
            day_detail_line = ""
            if not is_static_external and metric_vm and getattr(metric_vm, "has_day_detail_line", False):
                usd_value = getattr(metric_vm, "fmt_usd_value", "")
                fx_caption = getattr(metric_vm, "fx_caption", "")
                day_detail_line = " / ".join(part for part in [usd_value, fx_caption] if part)
            day_color = self.__day_color(asset.diff_pct, metric_vm)
            metrics_display_style = metric_vm.metrics_display_style if metric_vm else "display: block;"
            if is_static_external:
                fmt_day = "STATIC FACT"
                fmt_day_pct = ""
                day_color = _C_SLATE
                metrics_display_style = "display: none;"
            rows.append(
                V4LedgerRowViewModel(
                    name=asset.name,
                    asset_class=asset.asset_class,
                    source=asset.source,
                    fmt_value=f"{value:,}",
                    share_pct=share,
                    metric_capsule=" / ".join(capsule_parts),
                    value_color=_C_INK,
                    fmt_day=f"{fmt_day} / {fmt_day_pct}" if fmt_day_pct else fmt_day,
                    fmt_mtd=metric_vm.mtd if metric_vm else "---",
                    fmt_ytd=metric_vm.ytd if metric_vm else "---",
                    fmt_wtd=metric_vm.wtd if metric_vm else "---",
                    fmt_units=fmt_units,
                    fmt_price=fmt_price,
                    day_color=day_color,
                    metrics_display_style=metrics_display_style,
                    day_detail_line=day_detail_line,
                )
            )
        return rows

    def __row_value(self, row: V4LedgerRowViewModel) -> int:
        return int(row.fmt_value.replace(",", ""))

    def __fmt_units(self, units: float) -> str:
        rounded = round(units)
        if abs(units - rounded) < 1e-9:
            return f"{int(rounded):,}"
        return f"{units:,.6f}".rstrip("0").rstrip(".")

    def __fmt_price(self, price: float) -> str:
        rounded = round(price)
        if abs(price - rounded) < 1e-9:
            return f"{int(rounded):,}"
        return f"{price:,.2f}"

    def __is_static_external(self, asset: Any) -> bool:
        return (
            asset.source == "ABSOLUTE_AMOUNT"
            or asset.pricing_status == "STATIC"
            or asset.asset_class == "CASH_EXTERNAL"
            or asset.category == "CASH_EXTERNAL"
        )

    def __fmt_day_value(self, raw: Optional[float], metric_vm: Optional[PositionViewModel]) -> str:
        if raw is not None:
            return f"{int(round(raw)):+,}"
        return metric_vm.fmt_diff_jpy if metric_vm else "---"

    def __fmt_pct(self, raw: Optional[float], fallback: Optional[str] = None) -> str:
        if raw is not None:
            return f"{raw:+.2f}%"
        return fallback or "---"

    def __source_date_note(self, asset: Any) -> str:
        if asset.pricing_status != "STALE":
            return ""
        source_date = getattr(asset, "source_date", None)
        if not source_date:
            return ""
        try:
            parsed = datetime.strptime(str(source_date), "%Y-%m-%d")
        except ValueError:
            return ""
        return f" ({parsed.month}/{parsed.day})"

    def __day_color(self, raw_pct: Optional[float], metric_vm: Optional[PositionViewModel]) -> str:
        if raw_pct is not None:
            if raw_pct > 0:
                return _C_GOLD
            if raw_pct < 0:
                return _C_SLATE
            return _C_INK
        if not metric_vm:
            return _C_INK
        raw = metric_vm.fmt_diff_pct
        if raw.startswith("+") and not raw.startswith("+0"):
            return _C_GOLD
        if raw.startswith("-"):
            return _C_SLATE
        return _C_INK

    @property
    def __computed_state_label(self) -> str:
        abs_day = abs(self.__parse_pct(self.fmt_total_day_pct))
        safe_ratio = self.safe_ratio_pct
        missing_count = sum(1 for asset in self.__ledger.assets if asset.pricing_status == "MISSING")
        top_impact = self.__top_impact_score

        if abs_day >= 3.0 or safe_ratio < 15.0 or missing_count >= 3:
            return "BREAK"
        if abs_day >= 2.0 or safe_ratio < 25.0:
            return "STRESS"
        if abs_day >= 0.7 or top_impact >= 0.4 or missing_count > 0:
            return "WATCH"
        if abs_day < 0.15 and top_impact < 0.1:
            return "QUIET"
        return "NORMAL"

    @property
    def __computed_state_summary(self) -> str:
        label = self.__computed_state_label
        summaries = {
            "QUIET": "構造変化は観測されていません。",
            "NORMAL": "通常の揺れの範囲内です。",
            "WATCH": "偏りを観測。方針変更ではなく、確認対象として扱います。",
            "STRESS": "防衛状態への圧力を観測。新規判断は抑制します。",
            "BREAK": "方針再確認が必要な変動を観測しています。",
        }
        return summaries.get(label, summaries["NORMAL"])

    @property
    def __computed_primary_force(self) -> str:
        row = self.__top_impact_row
        if not row:
            return "MARKET SIGNAL / ---"
        return f"{row.name} / DAY {row.fmt_day}"

    @property
    def __top_impact_row(self) -> Optional[V4LedgerRowViewModel]:
        market_rows = [row for row in self.__rows if row.source == "MARKET_UNITS"]
        if not market_rows:
            return None
        return max(market_rows, key=self.__impact_score)

    @property
    def __top_impact_score(self) -> float:
        row = self.__top_impact_row
        return self.__impact_score(row) if row else 0.0

    @property
    def __top_impact_signed_score(self) -> float:
        row = self.__top_impact_row
        if not row:
            return 0.0
        day_pct = self.__parse_pct(self.__row_day_pct(row))
        return row.share_pct * day_pct / 100.0

    def __impact_score(self, row: V4LedgerRowViewModel) -> float:
        day_pct = self.__parse_pct(self.__row_day_pct(row))
        return abs(row.share_pct * day_pct / 100.0)

    def __row_day_pct(self, row: V4LedgerRowViewModel) -> str:
        return row.fmt_day.split(" / ", 1)[-1].split(" ", 1)[0]

    def __parse_pct(self, raw: str) -> float:
        try:
            return float(str(raw).replace("%", "").replace("+", "").replace(",", "").strip())
        except ValueError:
            return 0.0

    def __action_posture_for(self, label: str) -> str:
        postures = {
            "QUIET": "行動なし",
            "NORMAL": "行動なし",
            "WATCH": "追加判断は保留",
            "STRESS": "新規リスクを抑制",
            "BREAK": "方針を再確認",
        }
        return postures.get(label, "行動なし")

    @property
    def __market_regime(self) -> str:
        market_text = self.market_context
        vix = self.__extract_market_number(market_text, "VIX:")
        if vix >= 30:
            return "RISK_OFF"
        if vix >= 20:
            return "WATCHFUL"
        if vix > 0:
            return "CALM"
        return "UNKNOWN"

    @property
    def __fx_effect(self) -> str:
        market_text = self.market_context
        marker = "USD/JPY:"
        if marker not in market_text:
            return "UNKNOWN"
        after = market_text.split(marker, 1)[1]
        if "(+" in after:
            return "YEN_WEAKNESS"
        if "(-" in after:
            return "YEN_STRENGTH"
        return "MINOR"

    @property
    def __vix_band(self) -> str:
        vix = self.__extract_market_number(self.market_context, "VIX:")
        if vix >= 30:
            return "HIGH"
        if vix >= 20:
            return "ELEVATED"
        if vix > 0:
            return "CALM"
        return "UNKNOWN"

    @property
    def __monthly_tags(self) -> List[str]:
        tags = [self.state_label, self.__market_regime, self.__vix_band]
        causal_vector = str(self.__context.get("causality_vector") or "").strip()
        if causal_vector:
            tags.append(causal_vector)
        row = self.__top_impact_row
        if row:
            tags.append(row.asset_class)
        return [tag for tag in tags if tag and tag != "UNKNOWN"]

    @property
    def __archive_short_note(self) -> str:
        insight = self.__insight
        note = str(insight.get("analysis") or self.__context.get("overview") or self.state_summary)
        return note.replace("\n", " ")[:180]

    def __extract_market_number(self, text: str, marker: str) -> float:
        if marker not in text:
            return 0.0
        after = text.split(marker, 1)[1].strip()
        token = after.split(" ", 1)[0].replace("%", "").replace(",", "")
        try:
            return float(token)
        except ValueError:
            return 0.0
