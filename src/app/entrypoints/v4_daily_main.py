import argparse
import datetime
import sys
from typing import Final

from src.app.v4_engine import V4PortfolioEngine
from src.config.settings import APP_NAME, VERSION

__REV: Final[str] = "Rev. 1"


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {VERSION}: v4 Collection-Primary Portfolio Engine")

    parser.add_argument("date", nargs="?", help="Target Date (YYYY-MM-DD)")
    parser.add_argument("-r", "--rebuild", action="store_true", help="Reserved for CLI compatibility.")
    parser.add_argument("-f", "--fetch", action="store_true", help="Reserved for CLI compatibility (no-op in v4).")
    parser.add_argument("-F", "--force", action="store_true", help="Ignore CompletionLock and force send report")
    parser.add_argument("-u", "--use-cache", action="store_true", help="Reuse existing context cache if available")
    parser.add_argument("--scope", choices=["all", "index", "context"], default="all", help="Target report type")
    parser.add_argument("-o", "--offline", action="store_true", help="Reserved for CLI compatibility (no-op in v4).")
    parser.add_argument("-H", "--headless", action="store_true", default=False, help="Reserved for CLI compatibility (no-op in v4).")
    parser.add_argument("-t", "--format-test", action="store_true", help="Test Report Layout (Internal Rendering)")
    parser.add_argument("--test-error", action="store_true", help="Trigger Test Alert")
    parser.add_argument("--test-context", action="store_true", help="Trigger Context/Narrative Report Test")
    parser.add_argument("--test-market", action="store_true", help="Standalone MarketDataFetcher test (skips all other pipeline steps)")

    args = parser.parse_args()

    if args.test_market:
        from src.infra.market_data import MarketDataFetcher
        from src.lib.logger import setup_logger
        from src.lib.timeline_controller import TimelineController
        _logger = setup_logger(__name__)
        _timeline = TimelineController()
        _target = args.date if args.date else datetime.datetime.now().strftime("%Y-%m-%d")
        _us_date = _timeline.determine_us_market_date(_target)
        _logger.info(f"[Guard] --test-market: JP={_target}, US={_us_date}")
        _result = MarketDataFetcher().fetch_market_context(_us_date)
        _logger.info(f"[Outcome] {_result}")
        sys.exit(0)

    engine = V4PortfolioEngine()
    engine.run(
        target_date=args.date,
        offline=args.offline,
        headless=args.headless,
        force_fetch=args.fetch,
        force_rebuild=args.rebuild,
        force_send=args.force,
        scope=args.scope,
        format_test=args.format_test,
        test_error=args.test_error,
        test_context=args.test_context,
        reuse_context=args.use_cache,
    )


if __name__ == "__main__":
    main()
