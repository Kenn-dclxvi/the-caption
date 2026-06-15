from src.app.renderer.report_context import ContextRenderer


def _base_context_data() -> dict:
    return {
        "theme": "金利低下とテック再評価",
        "overview": "金利低下を背景にした反発。",
        "featured_assets": [],
        "implication": "補強候補はクオリティ株。",
        "shield_evaluation": "金属は連れ安で防壁性能は限定的。",
    }


def test_render_context_omits_portfolio_audit_for_legacy_cache():
    html = ContextRenderer().render(_base_context_data())

    assert "Portfolio Audit" not in html
    assert "補強候補はクオリティ株。" in html
    assert "金属は連れ安で防壁性能は限定的。" in html


def test_render_context_places_portfolio_audit_before_insight():
    data = _base_context_data()
    data["portfolio_audit"] = {
        "core_thesis": "STAY_COURSE",
        "cash_buffer": "EFFECTIVE",
        "stagnation_readiness": "HIGH",
        "summary": "現金比率が方針維持の余力を支え、コア仮説は今日の市場構造と矛盾していません。",
    }

    html = ContextRenderer().render(data)

    assert "Portfolio Audit" in html
    assert "Core Thesis: STAY_COURSE" in html
    assert "Cash: EFFECTIVE" in html
    assert "Stagnation: HIGH" in html
    assert html.index("Portfolio Audit") < html.index("補強候補はクオリティ株。")
    assert html.index("補強候補はクオリティ株。") < html.index("金属は連れ安で防壁性能は限定的。")


def test_render_context_omits_empty_portfolio_audit():
    data = _base_context_data()
    data["portfolio_audit"] = {
        "core_thesis": "",
        "cash_buffer": "",
        "stagnation_readiness": "",
        "summary": "",
    }

    html = ContextRenderer().render(data)

    assert "Portfolio Audit" not in html
    assert "補強候補はクオリティ株。" in html
