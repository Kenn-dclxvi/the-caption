import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.domain.universal_ingester import UniversalIngester
from src.infra.market_data import is_market_closed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the v4.0 shadow ledger ingester.")
    parser.add_argument("--date", dest="target_date", help="Target date in YYYY-MM-DD format.")
    parser.add_argument(
        "--output",
        default=os.path.join("data", "v4_shadow_ledger.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    ledger = UniversalIngester(is_closed_fn=is_market_closed).run(args.target_date, output_path=args.output)

    print(f"Wrote {args.output} ({len(ledger.assets)} assets, {ledger.total_value_jpy:,.0f} JPY)")


if __name__ == "__main__":
    main()
