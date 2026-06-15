import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Final, List, Tuple

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from src.config.settings import LLM_TRACE_FILE

_TOOL_REV: Final[str] = "Rev. 1"

_PRICING: Final[Dict[str, Tuple[float, float]]] = {
    "CLAUDE":   (3.00,  15.00),
    "DEEPSEEK": (0.14,   0.28),
    "GOOGLE":   (0.075,  0.30),
}

_LOG_PATTERN: Final[re.Pattern] = re.compile(
    r"\[(\d{4}-\d{2}-\d{2})[^\]]*\].*"
    r"\[Outcome\] Token Usage: provider=(\w+), input=(\d+), output=(\d+), ratio=[\d.]+(?:, elapsed=([\d.]+)s)?"
)

_MONTH_PATTERN: Final[re.Pattern] = re.compile(r"^\d{4}-\d{2}$")


def _collect_log_files(log_path: Path) -> List[Path]:
    files = [log_path] if log_path.exists() else []
    files += sorted(log_path.parent.glob(f"{log_path.name}.*"))
    return files


def _parse_logs(log_path: Path, target_month: str) -> Dict[str, dict]:
    stats: Dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "input": 0, "output": 0, "elapsed_sum": 0.0, "elapsed_count": 0}
    )
    for fpath in _collect_log_files(log_path):
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    m = _LOG_PATTERN.search(line)
                    if not m:
                        continue
                    date_str, provider, input_tok, output_tok, elapsed = m.groups()
                    if not date_str.startswith(target_month):
                        continue
                    p = stats[provider]
                    p["calls"] += 1
                    p["input"] += int(input_tok)
                    p["output"] += int(output_tok)
                    if elapsed is not None:
                        p["elapsed_sum"] += float(elapsed)
                        p["elapsed_count"] += 1
        except Exception as e:
            print(f"[Guard] Could not read {fpath}: {e}", file=sys.stderr)
    return stats


def _estimate_cost(provider: str, input_tok: int, output_tok: int) -> float:
    in_rate, out_rate = _PRICING.get(provider, (0.0, 0.0))
    return (input_tok / 1_000_000 * in_rate) + (output_tok / 1_000_000 * out_rate)


def _print_summary(stats: Dict[str, dict], target_month: str) -> None:
    print(f"\n=== API Cost Summary: {target_month} ===\n")
    if not stats:
        print("  No Token Usage records found for this month.")
        print()
        return

    hdr = f"  {'Provider':<12}{'Calls':>6}  {'Input Tok':>10}  {'Output Tok':>11}  {'Avg Elapsed':>12}  {'Est. Cost (USD)':>16}"
    sep = "  " + "-" * (len(hdr) - 2)
    print(hdr)
    print(sep)

    total_cost = 0.0
    for provider, p in sorted(stats.items()):
        cost = _estimate_cost(provider, p["input"], p["output"])
        total_cost += cost
        avg_elapsed = (p["elapsed_sum"] / p["elapsed_count"]) if p["elapsed_count"] > 0 else None
        elapsed_str = f"{avg_elapsed:.2f}s" if avg_elapsed is not None else "N/A"
        print(
            f"  {provider:<12}{p['calls']:>6}  {p['input']:>10,}  {p['output']:>11,}"
            f"  {elapsed_str:>12}  ${cost:>15.4f}"
        )

    print(sep)
    print(f"  {'Total':<12}{'':>6}  {'':>10}  {'':>11}  {'':>12}  ${total_cost:>15.4f}")
    print()
    pricing_note = " | ".join(
        f"{p} ${r[0]}/1M in, ${r[1]}/1M out"
        for p, r in sorted(_PRICING.items())
    )
    print(f"  * Pricing: {pricing_note}")
    print(f"  * Source : {LLM_TRACE_FILE} (+ rotated variants)")
    print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cost Summary — Monthly LLM token consumption and estimated API cost. "
            "Parses [Outcome] Token Usage lines from llm_trace.log."
        )
    )
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        default=datetime.now().strftime("%Y-%m"),
        help="Target month in YYYY-MM format (default: current month)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    target_month = args.month

    if not _MONTH_PATTERN.match(target_month):
        print(f"[Error] --month must be YYYY-MM format. Got: {target_month}", file=sys.stderr)
        sys.exit(1)

    log_path = Path(LLM_TRACE_FILE)
    stats = _parse_logs(log_path, target_month)
    _print_summary(stats, target_month)


if __name__ == "__main__":
    main()
