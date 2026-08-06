import json
import re
from typing import Optional, Dict, Any, List, Final
from src.lib.logger import setup_logger
from src.domain.ports import (
    IntelligenceTransporter,
    MonthlyInsightReader,
    ShadowLedgerHistoryStore,
)
from src.config.prompts import (
    MONTHLY_CHRONICLE_REPORT,
    CURATOR_BANNED_WORDS,
    MONTHLY_CHRONICLE_BANNED_WORDS,
    PROMPT_CHRONICLE_SYSTEM_V4,
    OUTPUT_SCHEMA_CHRONICLE_V4,
)
from src.lib.models import LedgerSummary
from src.domain.ledger_schema import ShadowLedger
from src.lib.utils import SystemUtils

logger = setup_logger(__name__)


class V4ChronicleSchemaViolation(RuntimeError):
    pass


class V4ChronicleBannedWordsViolation(RuntimeError):
    pass


class MonthlyCurator:
    __REV: Final[str] = "Rev. 6"

    def __init__(
        self,
        transporter: IntelligenceTransporter,
        insight_reader: MonthlyInsightReader,
        history_store: ShadowLedgerHistoryStore,
    ) -> None:
        logger.info(f"[{self.__REV}] Initializing MonthlyCurator")
        self.__transporter = transporter
        # generate_v4_chronicle は呼び出しごとの knowledge_manager を優先し、
        # 未指定時はここで注入された reader を使う。
        self.__insight_reader = insight_reader
        self.__history_store = history_store

    def generate_monthly_chronicle(self, year_month: str, summary: LedgerSummary, insights: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        logger.info(f"[Parsing] Generating Monthly Chronicle for {year_month} with {len(insights)} records")

        if len(insights) < 10:
            logger.warning(f"[Guard] The Void engaged: Only {len(insights)} records found for {year_month} (< 10). AI generation skipped.")
            return {}

        insight_stream_text = ""
        for record in insights:
            insight_stream_text += f"[{record['date']}]\n{record['content']}\n\n"

        prompt = MONTHLY_CHRONICLE_REPORT.format(
            year_month=year_month,
            insight_stream=insight_stream_text,
            safe_ratio=f"{summary.safe_ratio_pct:.1f}%"
        )

        return self.__execute_prompt(prompt)

    def generate_v4_chronicle(
        self,
        year_month: str,
        shadow_ledgers: Optional[List[ShadowLedger]] = None,
        insights: Optional[List[Dict[str, str]]] = None,
        daily_metrics: Optional[List[Dict[str, Any]]] = None,
        market_snapshots: Optional[List[Dict[str, Any]]] = None,
        ledger_paths: Optional[List[str]] = None,
        knowledge_manager: Optional[MonthlyInsightReader] = None,
    ) -> Dict[str, Any]:
        logger.info(f"[V4] Generating Monthly Chronicle for {year_month}")

        resolved_ledgers = shadow_ledgers if shadow_ledgers is not None else self.__load_v4_ledgers(year_month, ledger_paths)
        resolved_insights = insights if insights is not None else self.__load_v4_insights(year_month, knowledge_manager)
        resolved_metrics = daily_metrics or []
        resolved_market_snapshots = market_snapshots or []
        trend_summary = self.__aggregate_v4_ledgers(resolved_ledgers)
        metrics_summary = self.__aggregate_daily_metrics(resolved_metrics)
        market_snapshot_summary = self.__aggregate_market_snapshots(resolved_market_snapshots)
        context_summary = self.__aggregate_context_records(resolved_insights)

        prompt = self.__build_v4_prompt(
            year_month,
            resolved_insights,
            trend_summary,
            context_summary,
            metrics_summary,
            market_snapshot_summary,
        )
        raw_response = self.__request_v4_intelligence(prompt)
        parsed = self.__parse_v4_json(raw_response)
        self.__validate_v4_contract(parsed)
        self.__assert_v4_banned_words(parsed)

        return self.__normalize_v4_chronicle(
            parsed,
            year_month,
            trend_summary,
            context_summary,
            metrics_summary,
            market_snapshot_summary,
        )

    def __execute_prompt(self, prompt: str) -> Optional[Dict[str, Any]]:
        logger.info(f"[Acquisition] Executing monthly prompt (Size: {len(prompt)}, preview={prompt[:200]!r}...)")

        try:
            raw_response = self.__transporter.request_intelligence(prompt)
            logger.debug(f"[Parsing] Received AI response (size={len(raw_response)}, preview={raw_response[:200]!r}...)")

            json_content = SystemUtils.extract_json_from_response(raw_response)

            try:
                data = json.loads(json_content)

                violations = []
                all_text = [
                    data.get("theme_title", ""),
                    data.get("chronicle_headline", ""),
                    data.get("chronicle_body", ""),
                ]

                combined_text = " ".join(all_text)
                for word in CURATOR_BANNED_WORDS:
                    if word in combined_text:
                        violations.append(word)

                if violations:
                    violation_msg = f"Action Ban Violation: {violations}"
                    logger.error(f"[Audit] Censorship failed: {violation_msg}")
                    raise RuntimeError(violation_msg)

                logger.info("[Audit] Content integrity verified.")
                return data

            except json.JSONDecodeError as jde:
                logger.error(f"[Audit] JSON Decode Failed: {jde}")
                return None

        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.error(f"[Audit] Prompt execution exception: {e}")
            return None

    def __load_v4_insights(
        self,
        year_month: str,
        knowledge_manager: Optional[MonthlyInsightReader],
    ) -> List[Dict[str, str]]:
        manager = knowledge_manager or self.__insight_reader
        return manager.extract_monthly_insights(year_month)

    def __load_v4_ledgers(
        self,
        year_month: str,
        ledger_paths: Optional[List[str]],
    ) -> List[ShadowLedger]:
        paths = ledger_paths or self.__history_store.discover_shadow_ledger_paths()
        ledgers: List[ShadowLedger] = []

        for path in paths:
            try:
                payload = self.__history_store.read_shadow_ledger(path)
                ledger = ShadowLedger.model_validate(payload)
                if ledger.target_date.startswith(year_month):
                    ledgers.append(ledger)
            except Exception as exc:
                logger.warning(f"[V4] Skipping unreadable ShadowLedger history: {path} ({exc})")

        ledgers.sort(key=lambda ledger: ledger.target_date)
        return ledgers

    def __aggregate_v4_ledgers(self, ledgers: List[ShadowLedger]) -> Dict[str, Any]:
        if not ledgers:
            return {
                "ledger_days": 0,
                "start_total_jpy": 0,
                "end_total_jpy": 0,
                "total_change_jpy": 0,
                "total_change_pct": 0.0,
                "asset_class_trends": [],
            }

        buckets: Dict[str, Dict[str, float]] = {}
        start_total = ledgers[0].total_value_jpy
        end_total = ledgers[-1].total_value_jpy

        for asset in ledgers[0].assets:
            key = self.__v4_bucket_key(asset.source, asset.asset_class)
            buckets.setdefault(
                key,
                {
                    "source": asset.source,
                    "asset_class": asset.asset_class,
                    "start_value_jpy": 0.0,
                    "end_value_jpy": 0.0,
                },
            )
            buckets[key]["start_value_jpy"] += asset.current_value_jpy

        for asset in ledgers[-1].assets:
            key = self.__v4_bucket_key(asset.source, asset.asset_class)
            buckets.setdefault(
                key,
                {
                    "source": asset.source,
                    "asset_class": asset.asset_class,
                    "start_value_jpy": 0.0,
                    "end_value_jpy": 0.0,
                },
            )
            buckets[key]["end_value_jpy"] += asset.current_value_jpy

        trends: List[Dict[str, Any]] = []
        for bucket in buckets.values():
            start_value = bucket["start_value_jpy"]
            end_value = bucket["end_value_jpy"]
            change = end_value - start_value
            start_share = (start_value / start_total * 100) if start_total else 0.0
            end_share = (end_value / end_total * 100) if end_total else 0.0
            trends.append(
                {
                    "source": bucket["source"],
                    "asset_class": bucket["asset_class"],
                    "start_value_jpy": round(start_value),
                    "end_value_jpy": round(end_value),
                    "change_jpy": round(change),
                    "change_pct": round((change / start_value * 100), 2) if start_value else 0.0,
                    "start_share_pct": round(start_share, 2),
                    "end_share_pct": round(end_share, 2),
                    "share_delta_pct": round(end_share - start_share, 2),
                }
            )

        trends.sort(key=lambda row: (row["source"], row["asset_class"]))
        total_change = end_total - start_total
        return {
            "ledger_days": len(ledgers),
            "start_date": ledgers[0].target_date,
            "end_date": ledgers[-1].target_date,
            "start_total_jpy": round(start_total),
            "end_total_jpy": round(end_total),
            "total_change_jpy": round(total_change),
            "total_change_pct": round((total_change / start_total * 100), 2) if start_total else 0.0,
            "asset_class_trends": trends,
        }

    def __v4_bucket_key(self, source: str, asset_class: str) -> str:
        return f"{source}:{asset_class}"

    def __build_v4_prompt(
        self,
        year_month: str,
        insights: List[Dict[str, str]],
        trend_summary: Dict[str, Any],
        context_summary: Dict[str, Any],
        metrics_summary: Dict[str, Any],
        market_snapshot_summary: Dict[str, Any],
    ) -> str:
        insight_stream = "\n\n".join(
            f"[{record.get('date', 'unknown')}]\n{record.get('content', '')}"
            for record in insights
        )
        payload = {
            "year_month": year_month,
            "daily_insights": insight_stream,
            "daily_context_summary": context_summary,
            "daily_metrics_summary": metrics_summary,
            "market_snapshot_summary": market_snapshot_summary,
            "shadow_ledger_monthly_trend": trend_summary,
            "output_schema": OUTPUT_SCHEMA_CHRONICLE_V4,
        }
        return (
            "<user_payload>\n"
            f"  <target_month>{year_month}</target_month>\n"
            "  <daily_insights>\n"
            f"{json.dumps(payload['daily_insights'], ensure_ascii=False, indent=2)}\n"
            "  </daily_insights>\n"
            "  <daily_context_summary>\n"
            f"{json.dumps(payload['daily_context_summary'], ensure_ascii=False, indent=2)}\n"
            "  </daily_context_summary>\n"
            "  <daily_metrics_summary>\n"
            f"{json.dumps(payload['daily_metrics_summary'], ensure_ascii=False, indent=2)}\n"
            "  </daily_metrics_summary>\n"
            "  <market_snapshot_summary>\n"
            f"{json.dumps(payload['market_snapshot_summary'], ensure_ascii=False, indent=2)}\n"
            "  </market_snapshot_summary>\n"
            "  <monthly_trend_data>\n"
            f"{json.dumps(payload['shadow_ledger_monthly_trend'], ensure_ascii=False, indent=2)}\n"
            "  </monthly_trend_data>\n"
            "  <output_schema>\n"
            f"{json.dumps(payload['output_schema'], ensure_ascii=False, indent=2)}\n"
            "  </output_schema>\n"
            "</user_payload>\n"
            "<response_instruction>以下のV4月次コンテキストを読み解き、指定スキーマのJSONのみを返してください。</response_instruction>"
        )

    def __request_v4_intelligence(self, prompt: str) -> str:
        logger.info(f"[V4] Executing monthly chronicle prompt (Size: {len(prompt)})")
        return self.__transporter.request_intelligence(f"{PROMPT_CHRONICLE_SYSTEM_V4}\n\n{prompt}")

    def __parse_v4_json(self, raw_response: str) -> Dict[str, Any]:
        json_content = SystemUtils.extract_json_from_response(raw_response)
        try:
            return json.loads(json_content)
        except json.JSONDecodeError as exc:
            raise V4ChronicleSchemaViolation("V4 Chronicle schema violation: invalid JSON response") from exc

    def __validate_v4_contract(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise V4ChronicleSchemaViolation("V4 Chronicle schema violation: top-level response must be object")

        chronicle = data.get("chronicle")
        meta = data.get("meta")
        if not isinstance(chronicle, dict):
            raise V4ChronicleSchemaViolation("V4 Chronicle schema violation: chronicle must be object")
        if not isinstance(meta, dict):
            raise V4ChronicleSchemaViolation("V4 Chronicle schema violation: meta must be object")

        required_chronicle = {
            "title": str,
            "monthly_summary": str,
            "market_causality": str,
            "phase_analysis": list,
            "asset_contribution": list,
            "portfolio_audit": str,
            "next_month_watch": list,
        }
        required_meta = {
            "dominant_regime": str,
            "primary_causality": str,
            "fx_impact": str,
            "risk_temperature": str,
            "data_quality": str,
        }

        for field, expected_type in required_chronicle.items():
            if field not in chronicle:
                raise V4ChronicleSchemaViolation(f"V4 Chronicle schema violation: chronicle.{field} missing")
            if not isinstance(chronicle[field], expected_type):
                raise V4ChronicleSchemaViolation(f"V4 Chronicle schema violation: chronicle.{field} type mismatch")

        for field, expected_type in required_meta.items():
            if field not in meta:
                raise V4ChronicleSchemaViolation(f"V4 Chronicle schema violation: meta.{field} missing")
            if not isinstance(meta[field], expected_type):
                raise V4ChronicleSchemaViolation(f"V4 Chronicle schema violation: meta.{field} type mismatch")

        for field in ("phase_analysis", "asset_contribution", "next_month_watch"):
            if any(not isinstance(item, str) for item in chronicle[field]):
                raise V4ChronicleSchemaViolation(f"V4 Chronicle schema violation: chronicle.{field} items must be strings")

    def __assert_v4_banned_words(self, data: Dict[str, Any]) -> None:
        chronicle = data.get("chronicle", {})
        fields = [
            chronicle.get("title", ""),
            chronicle.get("monthly_summary", ""),
            chronicle.get("market_causality", ""),
            chronicle.get("portfolio_audit", ""),
            " ".join(chronicle.get("phase_analysis", [])),
            " ".join(chronicle.get("asset_contribution", [])),
            " ".join(chronicle.get("next_month_watch", [])),
        ]
        combined_text = " ".join(str(field) for field in fields)
        violations = [word for word in MONTHLY_CHRONICLE_BANNED_WORDS if word in combined_text]
        if violations:
            violation_msg = f"V4 Chronicle banned words violation: Action Ban Violation: {violations}"
            logger.error(f"[Audit] V4 censorship failed: {violation_msg}")
            raise V4ChronicleBannedWordsViolation(violation_msg)

    def __normalize_v4_chronicle(
        self,
        data: Dict[str, Any],
        year_month: str,
        trend_summary: Dict[str, Any],
        context_summary: Dict[str, Any],
        metrics_summary: Dict[str, Any],
        market_snapshot_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        chronicle = data.get("chronicle", data)
        meta = data.get("meta", {})
        monthly_summary = chronicle.get("monthly_summary") or chronicle.get("overview", "")
        market_causality = chronicle.get("market_causality") or chronicle.get("structural_change", "")
        total_path = metrics_summary.get("total_path") or {}
        has_ledger_trend = int(trend_summary.get("ledger_days", 0) or 0) > 0
        start_total_jpy = trend_summary.get("start_total_jpy", 0)
        end_total_jpy = trend_summary.get("end_total_jpy", 0)
        total_change_jpy = trend_summary.get("total_change_jpy", 0)
        total_change_pct = trend_summary.get("total_change_pct", 0.0)

        if not has_ledger_trend and total_path:
            start_total_jpy = total_path.get("start_total_jpy", 0)
            end_total_jpy = total_path.get("end_total_jpy", 0)
            total_change_jpy = total_path.get("change_jpy", 0)
            total_change_pct = total_path.get("change_pct", 0.0)

        return {
            "schema_version": "v4.1-monthly-chronicle",
            "chronicle": {
                "title": chronicle.get("title", "Monthly Chronicle"),
                "monthly_summary": monthly_summary,
                "overview": monthly_summary,
                "market_causality": market_causality,
                "structural_change": market_causality,
                "phase_analysis": chronicle.get("phase_analysis", []),
                "asset_contribution": chronicle.get("asset_contribution", []),
                "shield_review": chronicle.get("shield_review", ""),
                "portfolio_audit": chronicle.get("portfolio_audit", ""),
                "next_month_watch": chronicle.get("next_month_watch", []),
            },
            "meta": {
                "year_month": year_month,
                "ledger_days": trend_summary.get("ledger_days", 0),
                "metrics_days": metrics_summary.get("metrics_days", 0),
                "asset_class_trends": trend_summary.get("asset_class_trends", []),
                "daily_context_summary": context_summary,
                "daily_metrics_summary": metrics_summary,
                "market_snapshot_summary": market_snapshot_summary,
                "start_total_jpy": start_total_jpy,
                "end_total_jpy": end_total_jpy,
                "total_change_jpy": total_change_jpy,
                "total_change_pct": total_change_pct,
                "dominant_regime": meta.get("dominant_regime", ""),
                "primary_causality": meta.get("primary_causality", ""),
                "fx_impact": meta.get("fx_impact", ""),
                "risk_temperature": meta.get("risk_temperature", ""),
                "data_quality": meta.get("data_quality", metrics_summary.get("data_quality_label", "")),
            },
        }

    def __aggregate_daily_metrics(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {
                "metrics_days": 0,
                "total_path": {},
                "source_path": {},
                "top_contributors": [],
                "anomaly_days": [],
                "turning_points": [],
                "data_quality_label": "NO_DAILY_METRICS",
            }

        sorted_records = sorted(records, key=lambda row: str(row.get("target_date", "")))
        start = sorted_records[0]
        end = sorted_records[-1]
        top_moves: List[Dict[str, Any]] = []
        anomaly_days: List[Dict[str, Any]] = []

        for row in sorted_records:
            target_date = str(row.get("target_date", ""))
            missing_count = int(row.get("pricing_missing_count", 0) or 0)
            if missing_count:
                anomaly_days.append({"date": target_date, "reason": "MISSING_PRICING", "count": missing_count})
            for mover in row.get("top_movers", []) or []:
                move = dict(mover)
                move["date"] = target_date
                top_moves.append(move)

        top_moves.sort(key=lambda row: abs(float(row.get("diff_val_jpy") or 0)), reverse=True)
        turning_points = [
            {
                "date": row.get("target_date", ""),
                "total_value_jpy": row.get("total_value_jpy", 0),
                "market_units_value_jpy": row.get("market_units_value_jpy", 0),
                "absolute_amount_value_jpy": row.get("absolute_amount_value_jpy", 0),
            }
            for row in sorted_records
            if row is start or row is end or row.get("pricing_missing_count", 0)
        ]

        start_total = float(start.get("total_value_jpy") or 0)
        end_total = float(end.get("total_value_jpy") or 0)
        missing_days = len(anomaly_days)
        return {
            "metrics_days": len(sorted_records),
            "start_date": start.get("target_date", ""),
            "end_date": end.get("target_date", ""),
            "total_path": {
                "start_total_jpy": round(start_total),
                "end_total_jpy": round(end_total),
                "change_jpy": round(end_total - start_total),
                "change_pct": round(((end_total - start_total) / start_total * 100), 2) if start_total else 0.0,
            },
            "source_path": {
                "market_units_start_jpy": round(float(start.get("market_units_value_jpy") or 0)),
                "market_units_end_jpy": round(float(end.get("market_units_value_jpy") or 0)),
                "absolute_amount_start_jpy": round(float(start.get("absolute_amount_value_jpy") or 0)),
                "absolute_amount_end_jpy": round(float(end.get("absolute_amount_value_jpy") or 0)),
            },
            "top_contributors": top_moves[:10],
            "anomaly_days": anomaly_days,
            "turning_points": turning_points,
            "data_quality_label": "HAS_MISSING_PRICING" if missing_days else "OK",
        }

    def __aggregate_market_snapshots(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {
                "snapshot_days": 0,
                "daily_market_summaries": [],
            }

        sorted_records = sorted(records, key=lambda row: str(row.get("target_date", "")))
        daily_summaries: List[Dict[str, Any]] = []
        holiday_days: List[str] = []
        missing_summary_days: List[str] = []

        for row in sorted_records:
            target_date = str(row.get("target_date", ""))
            us_market = row.get("us_market", {})
            if not isinstance(us_market, dict):
                us_market = {}
            market_summary = str(row.get("market_summary", "") or "")
            if us_market.get("is_holiday"):
                holiday_days.append(target_date)
            if not market_summary:
                missing_summary_days.append(target_date)
            daily_summaries.append(
                {
                    "target_date": target_date,
                    "us_trading_date": us_market.get("trading_date", ""),
                    "is_holiday": bool(us_market.get("is_holiday", False)),
                    "market_summary": market_summary,
                    "market_observations": self.__parse_market_observations(market_summary),
                }
            )

        return {
            "snapshot_days": len(sorted_records),
            "start_date": daily_summaries[0]["target_date"],
            "end_date": daily_summaries[-1]["target_date"],
            "holiday_days": holiday_days,
            "missing_summary_days": missing_summary_days,
            "daily_market_summaries": daily_summaries,
        }

    def __parse_market_observations(self, market_summary: str) -> Dict[str, Any]:
        observations: Dict[str, Any] = {
            "indices": {},
            "us_10y_yield": None,
            "usd_jpy": None,
            "vix": None,
        }
        if not market_summary:
            return observations

        index_labels = {"S&P500", "NASDAQ100", "SOX"}
        for segment in market_summary.split("|"):
            label, separator, raw_value = segment.partition(":")
            if not separator:
                continue
            label = label.strip()
            raw_value = raw_value.strip()
            primary_value = self.__extract_market_number(raw_value)
            secondary_value = self.__extract_parenthetical_market_number(raw_value)
            if primary_value is None:
                continue

            if label in index_labels:
                observations["indices"][label] = {"change_pct": primary_value}
            elif label == "米10年債":
                observations["us_10y_yield"] = {
                    "yield_pct": primary_value,
                    "change": secondary_value,
                }
            elif label == "USD/JPY":
                observations["usd_jpy"] = {
                    "rate": primary_value,
                    "change_pct": secondary_value,
                }
            elif label == "VIX":
                observations["vix"] = {
                    "level": primary_value,
                    "change": secondary_value,
                }

        return observations

    def __extract_market_number(self, value: str) -> float | None:
        match = re.search(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", value)
        if not match:
            return None
        return float(match.group(0).replace(",", ""))

    def __extract_parenthetical_market_number(self, value: str) -> float | None:
        match = re.search(r"\(([-+]?\d+(?:,\d{3})*(?:\.\d+)?)%?\)", value)
        if not match:
            return None
        return float(match.group(1).replace(",", ""))

    def __aggregate_context_records(self, insights: List[Dict[str, str]]) -> Dict[str, Any]:
        state_counts: Dict[str, int] = {}
        primary_counts: Dict[str, int] = {}
        causal_counts: Dict[str, int] = {}
        tag_counts: Dict[str, int] = {}
        shield_counts: Dict[str, int] = {}
        policy_counts: Dict[str, int] = {}
        notes: List[Dict[str, str]] = []

        for record in insights:
            content = record.get("content", "")
            state_line = self.__extract_kb_field(content, "State")
            archive_line = self.__extract_kb_field(content, "Archive")
            archive_note = self.__extract_kb_field(content, "Archive Note")

            state_parts = [part.strip() for part in state_line.split("|") if part.strip()]
            if state_parts:
                self.__increment(state_counts, state_parts[0])
            if len(state_parts) > 1:
                primary_name = state_parts[1].split(" / DAY", 1)[0].strip()
                self.__increment(primary_counts, primary_name)
            if len(state_parts) > 2:
                self.__increment(policy_counts, state_parts[2])
            if len(state_parts) > 3:
                self.__increment(shield_counts, state_parts[3])

            archive_parts = [part.strip() for part in archive_line.split("|") if part.strip()]
            if archive_parts:
                self.__increment(causal_counts, archive_parts[0])
            if len(archive_parts) >= 5:
                for tag in archive_parts[4].split(","):
                    if tag.strip():
                        self.__increment(tag_counts, tag.strip())
            if archive_note:
                notes.append({"date": record.get("date", ""), "note": archive_note})

        return {
            "state_distribution": state_counts,
            "primary_forces": primary_counts,
            "causal_vectors": causal_counts,
            "policy_distribution": policy_counts,
            "shield_distribution": shield_counts,
            "monthly_tags": tag_counts,
            "archive_notes": notes,
        }

    def __extract_kb_field(self, content: str, field: str) -> str:
        match = re.search(rf"- \*\*{re.escape(field)}\*\*: (.*)", content)
        return match.group(1).strip() if match else ""

    def __increment(self, bucket: Dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1
