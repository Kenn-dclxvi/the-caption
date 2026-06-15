from unittest.mock import patch

from src.app.renderer.v4_content_renderer import V4ContentRenderer
from src.app.renderer.v4_view_models import V4MonolithicViewModel
from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.app.renderer.view_models import PositionViewModel, SummaryViewModel
from src.config.settings import VERSION
from src.lib.models import LedgerSummary, Position


def _shadow():
    return ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=3000,
        basis_active_key="2026-04",
        return_base_value_jpy=2000,
        total_acquisition_cost_jpy=1500,
        total_return_jpy=500,
        total_return_pct=33.3333333333,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Very Long Mutual Fund Name That Must Truncate In One Line",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                units=2,
                price=1000,
                source_symbol="FUND_A",
                current_value_jpy=2000,
                diff_val_jpy=45,
                diff_pct=2.25,
                mtd_pct=2.0,
                ytd_pct=3.0,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="ABSOLUTE_AMOUNT",
                name="Cash",
                asset_class="CASH_EXTERNAL",
                category="CASH_EXTERNAL",
                current_value_jpy=1000,
                pricing_status="STATIC",
            ),
        ],
    )


def test_v4_monolithic_renderer_contains_all_five_phases():
    context = {
        "theme": "Evening Thesis",
        "overview": "Causal line one\nCausal line two",
        "shield_evaluation": "Shield text",
        "portfolio_audit": {
            "core_thesis": "STAY_COURSE",
            "cash_buffer": "EFFECTIVE",
            "stagnation_readiness": "HIGH",
            "summary": "Audit text",
        },
        "state_classification": {
            "label": "NORMAL",
            "summary": "通常の揺れの範囲内",
            "primary_force": "FUND_A / DAY +45 / +2.25%",
            "action_posture": "行動なし",
        },
        "meta": {"theme_code": "BULL", "total_return": "+123"},
    }
    html = V4ContentRenderer().render(V4MonolithicViewModel(_shadow(), context))

    assert "Evening Anchor" not in html
    assert "DAILY PORTFOLIO APPRAISAL" in html
    assert "State / Primary" in html
    assert "NORMAL" in html
    assert "Evening Thesis" in html
    assert "Total Net Assets" in html
    assert "Context Record" not in html
    assert "Policy" not in html
    assert "UNIFIED LEDGER" not in html
    assert "Exposure" in html
    assert "Iron Bank" in html
    assert "Shield" not in html
    assert "Very Long Mutual Fund Name" in html
    assert "white-space:nowrap; overflow:hidden; text-overflow:ellipsis" in html
    assert "UNITS 2" in html
    assert "PRICE 1,000" in html
    assert "MUTUAL_FUNDS / PRICED" not in html


def test_v4_monolithic_footer_uses_app_version_without_ledger_schema_version():
    class FooterTemplate:
        def __init__(self, source):
            self.source = source

        def render(self, **kwargs):
            return self.source.replace("{{ vm.footer_label }}", kwargs["vm"].footer_label)

    shadow = _shadow()
    with patch("src.app.renderer.v4_content_renderer.Template", FooterTemplate):
        html = V4ContentRenderer().render(V4MonolithicViewModel(shadow, {}))

    assert f"THE CAPTION {VERSION}" in html
    assert shadow.schema_version not in html


def test_v4_monolithic_renderer_formats_decimal_price_to_two_places():
    shadow = ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=3000,
        basis_active_key="2026-04",
        return_base_value_jpy=2000,
        total_acquisition_cost_jpy=1500,
        total_return_jpy=500,
        total_return_pct=33.3333333333,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Decimal Price Fund",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                units=2,
                price=87543.2,
                source_symbol="FUND_A",
                current_value_jpy=3000,
                diff_val_jpy=45,
                diff_pct=2.25,
                mtd_pct=2.0,
                ytd_pct=3.0,
                pricing_status="PRICED",
            )
        ],
    )
    html = V4ContentRenderer().render(V4MonolithicViewModel(shadow, {}))

    assert "PRICE 87,543.20" in html
    assert "PRICE 87,543.200000" not in html


def test_v4_monolithic_renderer_uses_adapter_supplied_shadow_metrics():
    shadow = _shadow()
    ledger = ShadowLedgerAdapter().to_legacy_ledger(shadow)
    summary_vm = SummaryViewModel(ledger.summary)
    asset_vms = [PositionViewModel(position) for position in ledger.assets]

    html = V4ContentRenderer().render(V4MonolithicViewModel(shadow, {}, summary_vm=summary_vm, asset_vms=asset_vms))

    assert "YTD +3.00%" in html
    assert "MTD +2.00%" in html
    assert "DAY" in html
    assert "STATIC FACT" not in html
    assert "font-size:40px; font-weight:100; color:#1e293b" in html
    assert "white-space:nowrap; color:#64748b; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8; margin-top:2px;" in html
    assert "DAY <span style='color:#c5a059;'>+45" in html
    assert "font-size:11px; color:#64748b;'>/</span>" in html
    assert "+2.25%" in html
    assert "+500" in html


def test_v4_total_net_assets_day_uses_slate_slash():
    template_source = V4ContentRenderer()._V4ContentRenderer__template_path.read_text(encoding="utf-8")

    assert '<div style="white-space:nowrap; color:{{ c_slate }}; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8; margin-top:2px;"><span style="color:{{ c_slate }};">DAY</span>&nbsp;&nbsp;<span style="color:{{ vm.day_color }};">{{ vm.fmt_total_day }}</span> <span style="font-size:11px; margin:0 4px; color:{{ c_slate }};">/</span> <span style="color:{{ vm.day_color }};">{{ vm.fmt_total_day_pct }}</span></div>' in template_source


def test_v4_exposure_day_uses_same_two_line_structure():
    template_source = V4ContentRenderer()._V4ContentRenderer__template_path.read_text(encoding="utf-8")

    assert '<span style="white-space:nowrap;"><span style="color:{{ c_slate }};">WTD</span>&nbsp;&nbsp;{{ row.fmt_wtd }}</span>' in template_source
    assert '<div style="white-space:nowrap; color:{{ c_slate }}; font-size:12px; font-weight:300; letter-spacing:0.05em; line-height:1.8; margin-top:2px;"><span style="color:{{ c_slate }};">DAY</span>&nbsp;&nbsp;<span style="color:{{ row.day_color }};">{{ row.fmt_day.split(\' / \', 1)[0] }}</span>{% if \' / \' in row.fmt_day %}&nbsp;&nbsp;<span style="font-size:11px; color:{{ c_slate }};">/</span>&nbsp;&nbsp;<span style="color:{{ row.day_color }};">{{ row.fmt_day.split(\' / \', 1)[1] }}</span>{% endif %}</div>' in template_source


def test_v4_monolithic_renderer_maps_v4_schema_and_restores_v3_metrics():
    summary_vm = SummaryViewModel(
        LedgerSummary(
            total_assets_jpy=3000,
            total_profit_loss_jpy=123,
            cash_position_jpy=1000,
            total_diff_jpy=45,
            total_diff_pct=1.50,
            total_profit_loss_pct=4.10,
            invested_capital_jpy=2000,
            capital_gain_jpy=123,
            exposure_jpy=2000,
            iron_bank_jpy=1000,
            safe_ratio_pct=33.3,
            damper_coef=0.666,
            total_wtd="+1.00%",
            total_mtd="+2.00%",
            total_ytd="+3.00%",
        )
    )
    asset_vms = [
        PositionViewModel(
            Position(
                id="Very Long Mutual Fund Name That Must Truncate In One Line",
                name="Very Long Mutual Fund Name That Must Truncate In One Line",
                raw_name="Very Long Mutual Fund Name That Must Truncate In One Line",
                asset_class="MUTUAL_FUNDS",
                category="INVESTMENT",
                quantity=2,
                unit_price=1000,
                current_price=1000,
                currency="JPY",
                value_jpy=2000,
                acquisition_price=1800,
                profit_loss=200,
                profit_loss_pct=11.1,
                prev_day_diff_jpy=45,
                prev_day_diff_pct=2.25,
                is_nisa=False,
                is_specific=False,
                share=66.7,
                wtd="+1.00%",
                mtd="+2.00%",
                ytd="+3.00%",
            )
        ),
        PositionViewModel(
            Position(
                id="Cash",
                name="Cash",
                raw_name="Cash",
                asset_class="SHORT_TERM",
                category="CASH",
                quantity=0,
                unit_price=0,
                current_price=0,
                currency="JPY",
                value_jpy=1000,
                acquisition_price=1000,
                profit_loss=0,
                profit_loss_pct=0.0,
                prev_day_diff_jpy=0,
                prev_day_diff_pct=0.0,
                is_nisa=False,
                is_specific=False,
                share=33.3,
            )
        ),
    ]
    context = {
        "portfolio_audit": {
            "core_thesis": "方針維持",
            "cash_buffer": "適正",
            "stagnation_readiness": "高",
            "commentary": "V4 audit text",
        },
        "insight": {
            "theme": "V4 Thesis",
            "analysis": "V4 analysis",
            "vix_vector": "VIX is calm",
        },
        "shield_evaluation": {"status": "中立", "commentary": "V4 shield text"},
        "market_context": {
            "market_summary": "VIX: 19.31 | USD/JPY: 159.49 | SOX: 3.00% | S&P500: 1.00% | 米10年債: 4.00% | NASDAQ100: 2.00%"
        },
    }

    html = V4ContentRenderer().render(
        V4MonolithicViewModel(_shadow(), context, summary_vm=summary_vm, asset_vms=asset_vms)
    )

    assert "Safe Ratio" in html
    assert "33.3%" in html
    assert html.index("Safe Ratio") < html.index("Total Net Assets")
    assert html.index("Total Return") < html.index("Total Net Assets")
    assert html.index("Total Net Assets") < html.rindex("Exposure")
    assert "Exposure" in html
    assert "Iron Bank" in html
    assert "Exposure" in html
    assert "Iron Bank" in html
    assert "UNIFIED LEDGER" not in html
    assert "Total Return" in html
    assert "DAY" in html
    assert "YTD" in html
    assert "MTD" in html
    assert "WTD" in html
    assert "Policy" not in html
    assert "方針維持 / 適正 / 高" not in html
    assert "Context Record" not in html
    assert "V4 analysis" not in html
    assert "VIX is calm" not in html
    assert "USD/JPY 159.49" not in html
    assert "VIX 19.31" not in html
    assert "中立" not in html
    assert "STATIC FACT" not in html
    assert "+45 / +2.25%" in html


def test_v4_title_uses_stable_appraisal_heading_and_theme_subtitle():
    context = {
        "insight": {
            "theme": "凪に揺れる技術の帆、金属は沈潜す",
            "analysis": "V4 analysis",
        }
    }

    vm = V4MonolithicViewModel(_shadow(), context)

    assert vm.theme_title == "DAILY PORTFOLIO APPRAISAL"
    assert vm.theme_subtitle == "凪に揺れる技術の帆、金属は沈潜す"


def test_v4_ledger_day_uses_shadow_record_metrics_without_adapter_vm():
    html = V4ContentRenderer().render(V4MonolithicViewModel(_shadow(), {}))

    assert "+45" in html
    assert "+2.25%" in html


def test_v4_stale_ledger_day_appends_source_date_note_to_pct_only():
    def vm_for_first_asset(update, summary_vm=None):
        shadow = _shadow()
        asset = shadow.assets[0].model_copy(update=update)
        return V4MonolithicViewModel(
            shadow.model_copy(update={"assets": [asset, shadow.assets[1]]}),
            {},
            summary_vm=summary_vm,
        )

    stale_vm = vm_for_first_asset({"pricing_status": "STALE", "source_date": "2026-06-08"})
    stale_row = stale_vm.ledger_rows[0]

    assert stale_row.fmt_day == "+45 / +2.25% (6/8)"
    assert stale_row.fmt_day.split(" / ", 1) == ["+45", "+2.25% (6/8)"]
    assert "+2.25% (6/8)" in V4ContentRenderer().render(stale_vm)

    priced_row = vm_for_first_asset(
        {"pricing_status": "PRICED", "source_date": "2026-06-08"}
    ).ledger_rows[0]

    assert priced_row.fmt_day == "+45 / +2.25%"

    for source_date in ("bad-date", "", None):
        vm = vm_for_first_asset({"pricing_status": "STALE", "source_date": source_date})
        row = vm.ledger_rows[0]

        assert row.fmt_day == "+45 / +2.25%"
        assert "+2.25%" in V4ContentRenderer().render(vm)

    summary_vm = SummaryViewModel(
        LedgerSummary(
            total_assets_jpy=3000,
            total_profit_loss_jpy=123,
            cash_position_jpy=1000,
            total_diff_jpy=10,
            total_diff_pct=0.10,
            total_profit_loss_pct=4.10,
            invested_capital_jpy=2000,
            capital_gain_jpy=123,
            exposure_jpy=2000,
            iron_bank_jpy=1000,
            safe_ratio_pct=33.3,
            damper_coef=0.666,
        )
    )
    stale_impact_vm = vm_for_first_asset(
        {"pricing_status": "STALE", "source_date": "2026-06-08"},
        summary_vm=summary_vm,
    )

    assert stale_impact_vm.archive_context["primary_impact_pt"] == 2.25
    assert stale_impact_vm.state_label == "WATCH"


def test_v4_iron_bank_assets_are_split_from_exposure_by_structure():
    html = V4ContentRenderer().render(V4MonolithicViewModel(_shadow(), {}))

    assert "CASH_EXTERNAL / STATIC / STATIC FACT" not in html
    assert "Static Base" not in html
    assert html.index("Very Long Mutual Fund Name") < html.index("Iron Bank")
    assert html.index("Cash") > html.index("Iron Bank")


def test_v4_appraisal_block_is_hidden_when_visibility_flag_is_false():
    context = {"appraisal_visibility": {"show": False}}
    html = V4ContentRenderer().render(V4MonolithicViewModel(_shadow(), context))

    assert "DAILY PORTFOLIO APPRAISAL" not in html
    assert "State / Primary" not in html
    assert "Total Net Assets" in html


def test_v4_total_return_is_blank_when_portfolio_basis_missing():
    shadow = _shadow().model_copy(
        update={
            "basis_active_key": None,
            "total_acquisition_cost_jpy": None,
            "total_return_jpy": None,
            "total_return_pct": None,
        }
    )

    vm = V4MonolithicViewModel(shadow, {"meta": {"total_return": "+0"}})

    assert vm.total_return_anchor == "---"


def test_v4_state_classification_falls_back_to_computed_observation():
    summary_vm = SummaryViewModel(
        LedgerSummary(
            total_assets_jpy=3000,
            total_profit_loss_jpy=123,
            cash_position_jpy=1000,
            total_diff_jpy=10,
            total_diff_pct=0.10,
            total_profit_loss_pct=4.10,
            invested_capital_jpy=2000,
            capital_gain_jpy=123,
            exposure_jpy=2000,
            iron_bank_jpy=1000,
            safe_ratio_pct=33.3,
            damper_coef=0.666,
        )
    )

    vm = V4MonolithicViewModel(_shadow(), {}, summary_vm=summary_vm)

    assert vm.state_label == "WATCH"
    assert vm.action_posture == "追加判断は保留"
    assert "偏り" in vm.state_summary
    assert vm.display_context["state"] == "WATCH"
    assert vm.archive_context["state"] == "WATCH"
    assert "monthly_tags" in vm.archive_context
