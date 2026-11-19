"""Record and replay the existing input port without reading next-day inputs."""
from copy import deepcopy
import io

import pandas as pd

from src.domain.fund_price_fallback import encoded, require


class FrozenLedgerInputs:
    METHODS = frozenset({"read_external_assets", "read_portfolio_basis", "resolve_snapshot_path",
                         "snapshot_exists", "read_units_snapshot", "read_market_units_columns",
                         "read_market_units", "read_history_frame"})

    def __init__(self, delegate=None, calls=None, overlays=None):
        self.delegate = delegate
        self.calls = deepcopy(calls or {})
        self.overlays = overlays or {}

    def __getattr__(self, name):
        if name not in self.METHODS:
            raise AttributeError(name)

        def call(*args):
            key = encoded([name, args])
            if self.delegate is not None:
                value = getattr(self.delegate, name)(*args)
                if isinstance(value, pd.DataFrame):
                    saved = {"type": "frame", "data": value.to_csv(index=False)}
                elif isinstance(value, set):
                    saved = {"type": "set", "data": sorted(value)}
                else:
                    saved = {"type": "json", "data": deepcopy(value)}
                self.calls[key] = saved
                return value
            require(key in self.calls, "frozen_input_missing")
            saved = self.calls[key]
            if saved["type"] == "frame":
                value = pd.read_csv(io.StringIO(saved["data"]), float_precision="round_trip")
                if name == "read_history_frame":
                    value[args[2]] = pd.to_datetime(value[args[2]])
            elif saved["type"] == "set":
                value = set(saved["data"])
            else:
                value = deepcopy(saved["data"])
            if name == "read_history_frame" and args[1] in self.overlays:
                require(args[2] == "基準日", "invalid_price_history")
                point = self.overlays[args[1]]
                row = pd.DataFrame({"基準日": [pd.Timestamp(point["date"])], "基準価額": [float(point["price"])]})
                if value is None:
                    value = row
                else:
                    value = pd.concat([value[value["基準日"] != pd.Timestamp(point["date"])], row], ignore_index=True)
                value = value.sort_values("基準日").reset_index(drop=True)
            return value
        return call


class RecordedMarketClose:
    def __init__(self, delegate=None, values=None):
        self.delegate = delegate
        self.values = deepcopy(values or {})

    def __call__(self, *args):
        key = encoded(args)
        if self.delegate is not None:
            self.values[key] = self.delegate(*args)
        require(key in self.values, "frozen_market_close_missing")
        return self.values[key]


class FrozenTimeline:
    def __init__(self, jp_date, us_date):
        self.jp_date, self.us_date = jp_date, us_date

    def determine_jp_market_date(self, _target):
        return self.jp_date

    def get_us_market_context(self, _target):
        return {"trading_date": self.us_date}
