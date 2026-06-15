import os
from unittest.mock import patch
from src.lib.utils import SystemUtils


class TestSetFlagAtomic:
    def test_roundtrip(self, tmp_path):
        path = str(tmp_path / "flag.txt")
        SystemUtils.set_flag(path, "2026-02-28")
        assert SystemUtils.get_flag(path) == "2026-02-28"

    def test_no_stray_temp_on_success(self, tmp_path):
        path = str(tmp_path / "flag.txt")
        SystemUtils.set_flag(path, "ok")
        names = {f.name for f in tmp_path.iterdir()}
        assert names == {"flag.txt"}

    def test_no_stray_temp_on_replace_failure(self, tmp_path):
        path = str(tmp_path / "flag.txt")
        with patch("src.lib.utils.os.replace", side_effect=OSError("disk full")):
            SystemUtils.set_flag(path, "fail")
        remaining = list(tmp_path.iterdir())
        assert remaining == []


class TestParsePctStr:
    def test_float_input(self):
        assert SystemUtils.parse_pct_str(1.23) == 1.23

    def test_int_input(self):
        assert SystemUtils.parse_pct_str(5) == 5.0

    def test_string_positive_with_sign_and_unit(self):
        assert SystemUtils.parse_pct_str("+1.23%") == 1.23

    def test_string_negative_with_sign_and_unit(self):
        assert SystemUtils.parse_pct_str("-0.50%") == -0.5

    def test_string_plain_float(self):
        assert SystemUtils.parse_pct_str("3.14") == 3.14

    def test_dash_returns_zero(self):
        assert SystemUtils.parse_pct_str("---") == 0.0

    def test_empty_string_returns_zero(self):
        assert SystemUtils.parse_pct_str("") == 0.0

    def test_invalid_string_returns_zero(self):
        assert SystemUtils.parse_pct_str("N/A") == 0.0

    def test_none_returns_zero(self):
        assert SystemUtils.parse_pct_str(None) == 0.0
