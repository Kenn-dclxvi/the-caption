import argparse
from typing import Final
from src.app.weekly_engine import WeeklyEngine
from src.lib.logger import setup_logger
from src.config.settings import APP_NAME, VERSION

__REV: Final[str] = "Rev. 1"
logger = setup_logger("WEEKLY_MAIN")

def main() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {VERSION}: Weekly Chronicle Engine")

    parser.add_argument("date", nargs="?", help="Target Date (YYYY-MM-DD)")
    parser.add_argument("-F", "--force", action="store_true", help="Ignore CompletionLock and force send report")
    parser.add_argument("-u", "--use-cache", action="store_true", help="Reuse existing chronicle cache if available")
    parser.add_argument("-t", "--format-test", action="store_true", help="Rendering test — save HTML to reports/weekly_format_test.html, skip email send")

    args = parser.parse_args()

    engine = WeeklyEngine()
    engine.run(
        target_date=args.date,
        force_send=args.force,
        reuse_context=args.use_cache,
        format_test=args.format_test,
    )

if __name__ == "__main__":
    main()
