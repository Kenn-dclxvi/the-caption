"""Pending price requests, price adoption, and replay of frozen daily inputs."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

from src.domain.fund_price_fallback import FundPriceError, decimal, digest, require, uuid, validate_candidate
from src.domain.ledger_schema import ShadowLedger
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.domain.universal_ingester import UniversalIngester
from src.domain.v4_ledger_finalizer import V4LedgerFinalizer
from src.infra.frozen_ledger_inputs import FrozenLedgerInputs, FrozenTimeline, RecordedMarketClose
from src.infra.fund_price_repository import FundPriceRepository


class FundPriceFallback:
    def __init__(self, repository, ledger_repository, clock=None):
        self.repository, self.ledger_repository = repository, ledger_repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def load_ledger(self, target):
        return self.ledger_repository.load_for_price_fallback(target)

    @classmethod
    def from_environment(cls, ledger_repository):
        directory = os.environ.get("CAPTION_FUND_PRICE_FALLBACK_STATE_DIR")
        if not directory:
            return None
        require(Path(directory).is_absolute(), "invalid_price_state_path")
        return cls(FundPriceRepository(directory), ledger_repository)

    @staticmethod
    def find(state, request_id):
        uuid(request_id)
        for calculation in state["calculations"].values():
            if request_id in calculation["requests"]:
                return calculation, calculation["requests"][request_id]
        raise FundPriceError("price_request_not_found")

    def capture(self, ledger, context, assets):
        """Called before any persistence/dispatch of a daily result with missing NAV.

        assets is an explicit asset_id/name allowlist resolved from current public
        Market Units identities; broker-specific mappings never enter this service.
        """
        pending = []
        names = set()
        for asset_id, name in assets.items():
            uuid(asset_id)
            require(name not in names, "ambiguous_price_asset")
            names.add(name)
            rows = [a for a in ledger.assets if a.name == name and a.source == "MARKET_UNITS"]
            require(len(rows) == 1 and rows[0].asset_class == "MUTUAL_FUNDS" and rows[0].currency == "JPY",
                    "invalid_price_asset")
            if rows[0].pricing_status in {"MISSING", "STALE"}:
                pending.append((asset_id, name))
        if not pending:
            return False
        require(bool(context.get("calls")), "frozen_input_missing")
        frozen = {**deepcopy(context), "shadow": ledger.model_dump(mode="json")}
        revision = digest(frozen)
        target = ledger.target_date
        with self.repository.transaction() as state:
            if target in state["calculations"]:
                return True  # Never replace the original daily input version.
            existing = self.load_ledger(target)
            if existing and existing.get("meta", {}).get("integrity_status") == "VERIFIED":
                return False
            requests = {}
            for asset_id, name in pending:
                request_id = str(uuid4())
                requests[request_id] = {"request_id": request_id, "asset_id": asset_id,
                    "target_price_date": ledger.jp_market_date, "request_revision": revision,
                    "currency": "JPY", "price_quote_units": 10000, "name": name,
                    "status": "pending", "candidate": None, "receipt": None}
            state["calculations"][target] = {"context": frozen, "input_digest": revision,
                "requests": requests, "status": "waiting_for_price", "prepared_document": None,
                "baseline_digest": digest(existing), "result_digest": None}
        return True

    @staticmethod
    def public(calculation, request):
        return {k: deepcopy(v) for k, v in request.items() if k != "name"} | {
            "calculation_date": calculation["context"]["shadow"]["target_date"],
            "calculation_status": calculation["status"], "input_digest": calculation["input_digest"],
            "result_digest": calculation["result_digest"]}

    def list_requests(self):
        with self.repository.transaction() as state:
            return {"requests": [self.public(c, r) for c in state["calculations"].values()
                                 for r in c["requests"].values() if r["status"] == "pending"]}

    def list_requests_for_date(self, target):
        with self.repository.transaction() as state:
            calculation = state["calculations"].get(target)
            return [self.public(calculation, r) for r in calculation["requests"].values()] if calculation else []

    def get(self, request_id):
        with self.repository.transaction() as state:
            calculation, request = self.find(state, request_id)
            if calculation["status"] == "completed":
                target = calculation["context"]["shadow"]["target_date"]
                require(digest(self.load_ledger(target)) == calculation["result_digest"], "ledger_readback_mismatch")
            return self.public(calculation, request)


    def waiting(self, target):
        with self.repository.transaction() as state:
            return target in state["calculations"]

    def adopt(self, request_id, candidate, key):
        uuid(key)
        with self.repository.transaction() as state:
            calculation, request = self.find(state, request_id)
            validate_candidate(candidate, request, self.clock())
            fingerprint = digest(candidate)
            if request["receipt"]:
                require(request["receipt"] == {"idempotency_key": key, "candidate_digest": fingerprint},
                        "price_candidate_conflict")
                return self.public(calculation, request)
            require(calculation["status"] not in {"completed", "correction_required"}, "calculation_closed")
            require(request["status"] == "pending", "price_already_adopted")
            request.update(status="adopted", candidate=deepcopy(candidate),
                           receipt={"idempotency_key": key, "candidate_digest": fingerprint})
            if all(r["status"] in {"adopted", "primary"} for r in calculation["requests"].values()):
                calculation["status"] = "ready"
            return self.public(calculation, request)

    def refresh_primary(self, target, input_repository):
        """Read only missing NAV points; retain every other original input."""
        with self.repository.transaction() as state:
            calculation = state["calculations"].get(target)
            if not calculation or calculation["status"] in {"completed", "correction_required"}:
                return
            history_dir = calculation["context"]["ingester"]["history_dir"]
            for request in calculation["requests"].values():
                if request["status"] != "pending":
                    continue
                frame = input_repository.read_history_frame(history_dir, request["name"], "基準日")
                if frame is None:
                    continue
                rows = frame[frame["基準日"].dt.strftime("%Y-%m-%d") == request["target_price_date"]]
                if len(rows) != 1:
                    continue
                price = str(rows.iloc[0]["基準価額"])
                decimal(price)
                request.update(status="primary", candidate={"price": price, "source": "primary"})
            if all(r["status"] in {"adopted", "primary"} for r in calculation["requests"].values()):
                calculation["status"] = "ready"

    def _replay(self, calculation):
        context = calculation["context"]
        require(digest(context) == calculation["input_digest"], "frozen_input_digest_mismatch")
        for r in calculation["requests"].values():
            require(r["request_revision"] == calculation["input_digest"], "price_request_mismatch")
            require(decimal(str(float(r["candidate"]["price"]))) == decimal(r["candidate"]["price"]),
                    "price_precision_unsupported")
            if r["status"] == "adopted":
                validate_candidate(r["candidate"], r, self.clock())
                require(r["receipt"]["candidate_digest"] == digest(r["candidate"]), "price_receipt_mismatch")
        overlays = {r["name"]: {"date": r["target_price_date"], "price": r["candidate"]["price"]}
                    for r in calculation["requests"].values()}
        original = ShadowLedger.model_validate(context["shadow"])
        timeline = FrozenTimeline(original.jp_market_date, context["us_date"])
        ingester = UniversalIngester(**context["ingester"], timeline=timeline,
            is_closed_fn=RecordedMarketClose(values=context["closed"]),
            input_store=FrozenLedgerInputs(calls=context["calls"], overlays=overlays))
        ledger = ingester.run(original.target_date, units_mode="strict", previous_records=context["previous_records"])
        ledger = V4LedgerFinalizer(timeline).finalize(ledger)
        ledger = ledger.model_copy(update={"generated_at": original.generated_at})
        require(all(a.pricing_status in {"PRICED", "STATIC"} for a in ledger.assets), "other_prices_unresolved")
        return ledger

    def delivery_ledger(self, target):
        with self.repository.transaction() as state:
            calculation = state["calculations"].get(target)
            if not calculation or calculation["status"] != "completed":
                return None
            ledger = self._replay(calculation)
            document = ShadowLedgerAdapter().to_canonical_document(ledger)
            require(digest(document) == calculation["result_digest"] == digest(self.load_ledger(target)),
                    "ledger_readback_mismatch")
            return ledger

    def claim_delivery(self, target):
        with self.repository.transaction() as state:
            calculation = state["calculations"][target]
            if calculation.get("delivery_status"):
                return False
            calculation["delivery_status"] = "smtp_result_unknown"
            return True

    def record_delivery(self, target):
        with self.repository.transaction() as state:
            state["calculations"][target]["delivery_status"] = "sent"

    def complete(self, request_id):
        # Phase 1 commits the computed document before any canonical publication.
        # Retrying phase 2 recovers a response loss with the identical document.
        with self.repository.transaction() as state:
            calculation, request = self.find(state, request_id)
            if calculation["status"] in {"completed", "correction_required", "waiting_for_price"}:
                return self.public(calculation, request)
            require(calculation["status"] in {"ready", "calculation_failed", "prepared"}, "invalid_calculation_state")
            if calculation["prepared_document"] is None:
                try:
                    ledger = self._replay(calculation)
                    calculation["prepared_document"] = ShadowLedgerAdapter().to_canonical_document(ledger)
                    calculation["status"] = "prepared"
                except Exception:
                    calculation["status"] = "calculation_failed"
                    return self.public(calculation, request)
        with self.repository.transaction() as state:
            calculation, request = self.find(state, request_id)
            if calculation["status"] == "completed":
                return self.public(calculation, request)
            document = calculation["prepared_document"]
            require(document is not None, "calculation_not_prepared")
            target = calculation["context"]["shadow"]["target_date"]
            existing = self.load_ledger(target)
            if digest(existing) != digest(document) and digest(existing) != calculation["baseline_digest"]:
                calculation["status"] = "correction_required"
                return self.public(calculation, request)
            if digest(existing) != digest(document):
                self.ledger_repository.save_for_price_fallback(document, target)
            require(digest(self.load_ledger(target)) == digest(document), "ledger_readback_mismatch")
            calculation["status"] = "completed"
            calculation["result_digest"] = digest(document)
            return self.public(calculation, request)


def capture_engine_price_wait(service, ledger, ingester, inputs, closed, previous_records, us_date):
    from src.infra.market_units_input_repository import MarketUnitsInputRepository
    requested = {s.strip() for s in os.environ.get("CAPTION_FUND_PRICE_FALLBACK_ASSETS", "").split(",") if s.strip()}
    require(bool(requested), "price_assets_not_configured")
    for asset_id in requested:
        uuid(asset_id)
    with MarketUnitsInputRepository(ingester.funds_csv_path).transaction() as session:
        selected = {r["asset_id"]: r["name"] for r in session.state["document"]["items"]
                    if r["asset_id"] in requested}
    require(set(selected) == requested, "unknown_price_asset")
    kwargs = {name: getattr(ingester, name) for name in ("funds_csv_path", "external_assets_path",
               "portfolio_basis_path", "history_dir", "units_snapshot_dir")}
    return service.capture(ledger, {"ingester": kwargs, "calls": inputs.calls, "closed": closed.values,
                                   "previous_records": previous_records, "us_date": us_date}, selected)
