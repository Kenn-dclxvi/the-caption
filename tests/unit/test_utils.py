import json
import os
from unittest.mock import patch

from src.lib.atomic_write import DEFAULT_NEW_FILE_MODE, atomic_write_json
from src.lib.utils import SystemUtils


class TestSetFlagAtomic:
    def test_roundtrip(self, tmp_path):
        path = str(tmp_path / "flag.txt")
        assert SystemUtils.set_flag(path, "2026-02-28") is True
        assert SystemUtils.get_flag(path) == "2026-02-28"

    def test_no_stray_temp_on_success(self, tmp_path):
        path = str(tmp_path / "flag.txt")
        assert SystemUtils.set_flag(path, "ok") is True
        names = {f.name for f in tmp_path.iterdir()}
        assert names == {"flag.txt"}

    def test_replace_failure_is_reported_and_preserves_previous_flag(self, tmp_path):
        path = str(tmp_path / "flag.txt")
        (tmp_path / "flag.txt").write_text("previous", encoding="utf-8")
        with patch("src.lib.utils.os.replace", side_effect=OSError("disk full")):
            result = SystemUtils.set_flag(path, "fail")
        assert result is False
        assert SystemUtils.get_flag(path) == "previous"
        assert {item.name for item in tmp_path.iterdir()} == {"flag.txt"}


class TestAtomicWriteJsonPermissions:
    def test_preserves_existing_destination_mode(self, tmp_path):
        path = tmp_path / "ledger.json"
        path.write_text('{"old":true}\n', encoding="utf-8")
        path.chmod(0o640)

        atomic_write_json(str(path), {"new": True})

        assert path.stat().st_mode & 0o777 == 0o640
        assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}

    def test_new_destination_uses_documented_deterministic_mode(self, tmp_path):
        path = tmp_path / "ledger.json"

        atomic_write_json(str(path), {"new": True})

        assert DEFAULT_NEW_FILE_MODE == 0o644
        assert path.stat().st_mode & 0o777 == DEFAULT_NEW_FILE_MODE


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
