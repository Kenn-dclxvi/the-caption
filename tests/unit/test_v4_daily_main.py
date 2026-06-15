from unittest.mock import patch

import pytest


def test_v4_daily_main_help_does_not_expose_with_ai(capsys):
    with patch("sys.argv", ["v4_daily_main.py", "-h"]):
        from src.app.entrypoints.v4_daily_main import main

        with pytest.raises(SystemExit):
            main()

    captured = capsys.readouterr()
    assert "--with-ai" not in captured.out


def test_v4_daily_main_does_not_forward_with_ai_to_engine():
    with patch("sys.argv", ["v4_daily_main.py", "2026-04-25"]), \
         patch("src.app.entrypoints.v4_daily_main.V4PortfolioEngine") as MockEngine:
        from src.app.entrypoints.v4_daily_main import main

        main()

    MockEngine.return_value.run.assert_called_once()
    assert "with_ai" not in MockEngine.return_value.run.call_args.kwargs
