import sys
from unittest.mock import patch

from src.app.renderer.report_collection import CollectionRenderer
from src.app.renderer.view_models import CollectionPositionViewModel, CollectionSummaryViewModel, CollectionSectionViewModel


def _make_summary() -> CollectionSummaryViewModel:
    return CollectionSummaryViewModel(
        total_value=1_000_000.0,
        total_diff_jpy=10_000.0,
        total_diff_pct=1.0,
        display_date="2026-02-25",
        fx_rate=150.25,
        fx_date="2026.02.25",
    )


def _make_position(
    name: str = "TEST FUND",
    code: str | None = None,
    asset_class: str = "MUTUAL_FUNDS",
    currency: str = "JPY",
    current_value: float | None = 2_345_678.0,
) -> CollectionPositionViewModel:
    metrics = {
        "asset_class": asset_class,
        "currency": currency,
        "current_value": current_value,
        "diff_val": 12_345.0,
        "diff_pct": 0.67,
        "m_pct": 1.2,
        "y_pct": 3.4,
        "share_pct": 10.0,
        "native_value": 2_345_678.0 if currency == "JPY" else 15_000.25,
        "fx_rate": 150.25 if currency == "USD" else None,
        "source_symbol": code or name,
        "code": code or name,
    }
    return CollectionPositionViewModel(name, metrics)


def test_render_collection_shows_day_amount_and_pct():
    fake_template = type(
        "FakeTemplate",
        (),
        {"render": lambda self, **kwargs: self.template},
    )()

    with patch("src.app.renderer.report_collection.Template") as mock_template:
        mock_template.return_value = fake_template
        fake_template.template = ""

        renderer = CollectionRenderer()
        renderer.render(
            _make_summary(),
            [
                CollectionSectionViewModel("Funds", "MUTUAL_FUNDS", [_make_position()]),
                CollectionSectionViewModel("US", "US_STOCK", [_make_position(asset_class="US_STOCK", currency="USD")]),
            ],
        )

        template_source = mock_template.call_args[0][0]

    assert 'white-space: nowrap;"><span style="color: {{ c_slate }};">DAY</span>' in template_source
    assert "<span style=\"color: {{ sum.day_color }};\">{{ sum.fmt_total_diff }}</span>" in template_source
    assert "<span style=\"color: {{ pos.day_color }};\">{{ pos.fmt_diff_jpy }}</span>" in template_source
    assert "{{ pos.fmt_diff_pct }}" in template_source
    assert ">Exposure</div>" in template_source
    assert "{{ pos.fx_caption }}" in template_source
    assert "{{ pos.fmt_usd_value }}" in template_source
    assert "<span style=\"color: {{ c_slate }};\">USD</span>" in template_source
    assert "{{ section.title }}" not in template_source
    assert "for pos in positions" in template_source
    assert "{{ sum.fmt_fx_reference }}" not in template_source


def test_render_collection_sorts_across_sections_by_value_then_code():
    saved_jinja2 = sys.modules.get("jinja2")
    try:
        if "jinja2" in sys.modules:
            del sys.modules["jinja2"]
        import jinja2 as real_jinja2
    finally:
        if saved_jinja2 is not None:
            sys.modules["jinja2"] = saved_jinja2

    with patch("src.app.renderer.report_collection.Template", real_jinja2.Template):
        renderer = CollectionRenderer()
        html = renderer.render(
            _make_summary(),
            [
                CollectionSectionViewModel("Funds", "MUTUAL_FUNDS", [
                    _make_position(name="Zulu Display", code="AAA", current_value=300_000.0),
                ]),
                CollectionSectionViewModel("US", "US_STOCK", [
                    _make_position(name="Alpha Display", code="ZZZ", asset_class="US_STOCK", currency="USD", current_value=300_000.0),
                    _make_position(name="Middle Display", code="MMM", asset_class="US_STOCK", currency="USD", current_value=100_000.0),
                    _make_position(name="Tail Display", code="NNN", asset_class="US_STOCK", currency="USD", current_value=None),
                ]),
            ],
        )

    assert html.index("Zulu Display") < html.index("Alpha Display") < html.index("Middle Display") < html.index("Tail Display")
