"""Private stdio transport for the existing Express HTTP gateway."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import threading

from src.app.input_api import InputApi, MAX_BODY_BYTES
from src.infra.input_api_credentials import CredentialFile
from src.infra.market_units_input_repository import MarketUnitsInputRepository


# JSON.stringify can expand each body byte into a six-byte \u00xx escape.
# The additional envelope budget covers Node's HTTP headers and request target.
MAX_FRAME_BYTES = MAX_BODY_BYTES * 6 + 128 * 1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", required=True)
    args = parser.parse_args()
    service = InputApi(
        MarketUnitsInputRepository(args.csv_path),
        CredentialFile(os.environ.get("CAPTION_API_CREDENTIALS_FILE")),
        allowed_price_hosts={host.strip().lower() for host in os.environ.get("CAPTION_API_PRICE_HOSTS", "").split(",") if host.strip()},
    )
    output_lock = threading.Lock()

    def dispatch(packet):
        result = service.handle(packet)
        encoded = json.dumps({"id": packet.get("id"), **result}, ensure_ascii=False, allow_nan=False)
        with output_lock:
            sys.stdout.write(encoded + "\n")
            sys.stdout.flush()

    with ThreadPoolExecutor(max_workers=4) as pool:
        while True:
            line = sys.stdin.buffer.readline(MAX_FRAME_BYTES)
            if not line:
                break
            try:
                packet = json.loads(line)
                if not isinstance(packet, dict) or not line.endswith(b"\n"):
                    raise ValueError("invalid packet")
            except (ValueError, RecursionError):
                # Only the local gateway can write this channel; fail closed on corrupt framing.
                break
            pool.submit(dispatch, packet)


if __name__ == "__main__":
    main()
