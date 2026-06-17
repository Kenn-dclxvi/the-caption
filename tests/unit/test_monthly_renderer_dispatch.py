from unittest.mock import MagicMock

from src.app.renderer import ContentRenderer


def test_content_renderer_uses_v4_monthly_only_for_schema_version() -> None:
    renderer = ContentRenderer()
    summary_vm = MagicMock()
    data = {"schema_version": "v4.1-monthly-chronicle", "chronicle": {}, "meta": {}}

    renderer._ContentRenderer__monthly.render_v4 = MagicMock(return_value="<v4>")
    renderer._ContentRenderer__monthly.render = MagicMock(return_value="<legacy>")

    assert renderer.render_monthly(data, summary_vm) == "<v4>"
    renderer._ContentRenderer__monthly.render_v4.assert_called_once_with(data, summary_vm)
    renderer._ContentRenderer__monthly.render.assert_not_called()


def test_content_renderer_keeps_chronicle_meta_payload_on_legacy_renderer_without_schema() -> None:
    renderer = ContentRenderer()
    summary_vm = MagicMock()
    data = {"chronicle": {}, "meta": {}}

    renderer._ContentRenderer__monthly.render_v4 = MagicMock(return_value="<v4>")
    renderer._ContentRenderer__monthly.render = MagicMock(return_value="<legacy>")

    assert renderer.render_monthly(data, summary_vm) == "<legacy>"
    renderer._ContentRenderer__monthly.render_v4.assert_not_called()
    renderer._ContentRenderer__monthly.render.assert_called_once_with(data, summary_vm)
