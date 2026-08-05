import os
import json
import re
import datetime
from typing import Optional, Dict, Any, List, Union, Final, Tuple

from src.lib.logger import setup_logger
from src.lib.models import Ledger, LedgerSummary, Position
from src.lib.guard import INJECTION_PATTERNS as _INJECTION_PATTERNS
from src.lib.utils import SystemUtils
from src.domain.ledger_schema import ShadowLedger
from src.domain.ports import IntelligenceTransporter, MarketContextReader
from src.lib.timeline_controller import TimelineController
from src.config.settings import DATA_DIR
from src.config.prompts import (
    CURATOR_EXHIBITION_REPORT,
    EXHIBITION_THEMES,
    CURATOR_BANNED_WORDS,
    US_MARKET_CONTEXT_NORMAL,
    US_MARKET_CONTEXT_HOLIDAY,
)

logger = setup_logger(__name__)

_VALID_CAUSALITY_VECTORS: Final[Tuple[str, ...]] = ("TECH_DRIVEN", "YIELD_PRESSURE", "YEN_IMPACT", "ROTATION", "FLAT")
_VALID_SHIELD_STATUSES: Final[Tuple[str, ...]] = ("ACTIVE", "CORRELATED", "NEUTRAL")
_VALID_CORE_THESES: Final[Tuple[str, ...]] = ("STAY_COURSE", "WATCH", "THESIS_REVIEW")
_VALID_CASH_BUFFERS: Final[Tuple[str, ...]] = ("EFFECTIVE", "ADEQUATE", "THIN", "UNKNOWN")
_VALID_STAGNATION_READINESS: Final[Tuple[str, ...]] = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
_TECH_ASSET_CLASSES: Final[Tuple[str, ...]] = ("MUTUAL_FUNDS", "US_STOCK")
_METAL_ASSET_CLASSES: Final[Tuple[str, ...]] = ("COMMODITIES",)
_CASH_ASSET_CLASSES: Final[Tuple[str, ...]] = ("SHORT_TERM", "CASH_EQUIVALENTS")
_MAX_VALIDATION_RETRIES: Final[int] = 3

class MarketCurator:
    __REV: Final[str] = "Rev. 94"

    def __init__(
        self,
        timeline: TimelineController,
        transporter: IntelligenceTransporter,
        market_fetcher: MarketContextReader,
    ) -> None:
        logger.info(f"[{self.__REV}] Initializing MarketCurator")
        self.__transporter = transporter
        self.__market_fetcher = market_fetcher
        self.__timeline = timeline

    def __sanitize_external(self, text: str) -> str:
        lower = text.lower()
        detected = [p for p in _INJECTION_PATTERNS if p.lower() in lower]
        if not detected:
            return text
        logger.warning(f"[Guard] Injection pattern detected in external content: {detected}")
        sanitized = text
        for p in detected:
            sanitized = re.sub(re.escape(p), "[REDACTED]", sanitized, flags=re.IGNORECASE)
        return sanitized

    def generate_context_report(self,
                                target_date: str,
                                summary: LedgerSummary,
                                assets: List[Position],
                                ledger: Optional[Ledger] = None) -> Optional[Dict[str, Any]]:
        logger.info(f"[Parsing] generate_context_report for {target_date}")
        return self.__generate_exhibition_report(target_date, summary, assets, ledger)

    def _get_context_dates(self, target_date: str) -> Dict[str, Any]:
        us_ctx = self.__timeline.get_us_market_context(target_date)

        trading_date_str  = us_ctx["trading_date"]
        calendar_date_str = us_ctx["calendar_date"]
        is_holiday        = us_ctx["is_holiday"]

        base_jp = datetime.datetime.strptime(target_date, "%Y-%m-%d")
        base_us = datetime.datetime.strptime(trading_date_str, "%Y-%m-%d")
        base_cal = datetime.datetime.strptime(calendar_date_str, "%Y-%m-%d")

        logger.info(
            f"[Parsing] Time-Sync: JP {target_date} -> "
            f"US Cal {calendar_date_str}, US Trade {trading_date_str}, "
            f"Holiday: {is_holiday}"
        )

        return {
            "jp_label":          f"{base_jp.month}/{base_jp.day}",
            "us_label":          f"{base_us.month}/{base_us.day}",
            "jp_full":           target_date,
            "us_full":           trading_date_str,
            "us_calendar_date":  calendar_date_str,
            "us_was_holiday":    is_holiday,
            "us_cal_label":      f"{base_cal.month}/{base_cal.day}",
        }

    def __determine_exhibition_theme(self, diff_pct: float) -> Tuple[str, str]:
        theme = ""
        angle = ""

        if diff_pct < -2.0:
            theme, angle = EXHIBITION_THEMES["CRASH"]
            logger.warning(f"[Guard] CRASH Detected (Diff: {diff_pct:.2f}%). Theme: {theme}")
        elif -2.0 <= diff_pct < -0.5:
            theme, angle = EXHIBITION_THEMES["BEAR"]
            logger.info(f"[Parsing] BEAR Detected (Diff: {diff_pct:.2f}%). Theme: {theme}")
        elif -0.5 <= diff_pct < 0.5:
            theme, angle = EXHIBITION_THEMES["FLAT"]
            logger.info(f"[Parsing] FLAT Detected (Diff: {diff_pct:.2f}%). Theme: {theme}")
        else:
            theme, angle = EXHIBITION_THEMES["BULL"]
            logger.info(f"[Parsing] BULL Detected (Diff: {diff_pct:.2f}%). Theme: {theme}")

        return theme, angle

    def __compute_actual_evidence(self, ledger: Ledger) -> Tuple[Optional[float], Optional[float]]:
        tech_value = 0.0
        tech_weighted = 0.0
        metal_value = 0.0
        metal_weighted = 0.0
        for p in ledger.assets:
            if p.category == "CASH":
                continue
            v = float(p.value_jpy)
            if p.asset_class in _TECH_ASSET_CLASSES:
                tech_value += v
                tech_weighted += p.prev_day_diff_pct * v
            elif p.asset_class in _METAL_ASSET_CLASSES:
                metal_value += v
                metal_weighted += p.prev_day_diff_pct * v
        tech_pct = tech_weighted / tech_value if tech_value > 0 else None
        metal_pct = metal_weighted / metal_value if metal_value > 0 else None
        return tech_pct, metal_pct

    def __is_single_edit_apart(self, source: str, candidate: str) -> bool:
        if source == candidate:
            return False

        source_len = len(source)
        candidate_len = len(candidate)
        if abs(source_len - candidate_len) > 1:
            return False

        if source_len == candidate_len:
            mismatch_count = sum(1 for left, right in zip(source, candidate) if left != right)
            return mismatch_count == 1

        longer, shorter = (source, candidate) if source_len > candidate_len else (candidate, source)
        long_idx = 0
        short_idx = 0
        mismatch_found = False
        while long_idx < len(longer) and short_idx < len(shorter):
            if longer[long_idx] == shorter[short_idx]:
                long_idx += 1
                short_idx += 1
                continue
            if mismatch_found:
                return False
            mismatch_found = True
            long_idx += 1
        return True

    def __resolve_asset_id(self, asset_id: str, known_asset_ids: List[str]) -> Tuple[Optional[str], Optional[str]]:
        if asset_id in known_asset_ids:
            return asset_id, None

        candidates = [candidate for candidate in known_asset_ids if self.__is_single_edit_apart(asset_id, candidate)]
        if len(candidates) == 1:
            return candidates[0], None
        if len(candidates) > 1:
            return None, f"複数候補に一致: {candidates}"
        return None, "既知 asset_id に一致しない"

    def __canonicalize_featured_assets(self, result: Dict[str, Any], id_data_map: Dict[str, Dict[str, Any]]) -> Tuple[bool, str]:
        featured_assets = result.get("featured_assets", [])
        if featured_assets is None:
            result["featured_assets"] = []
            return True, ""
        if not isinstance(featured_assets, list):
            return False, "featured_assets は配列でなければならない。"
        if not featured_assets:
            return True, ""
        if not id_data_map:
            return False, "featured_assets が返されたが、検証可能な asset_id が存在しない。"

        known_asset_ids = list(id_data_map.keys())
        errors: List[str] = []
        for index, asset in enumerate(featured_assets):
            if not isinstance(asset, dict):
                errors.append(f"featured_assets[{index}] はオブジェクトでなければならない。")
                continue

            raw_asset_id = str(asset.get("asset_id", "")).strip()
            if not raw_asset_id:
                errors.append(f"featured_assets[{index}].asset_id が空。")
                continue

            canonical_asset_id, resolve_error = self.__resolve_asset_id(raw_asset_id, known_asset_ids)
            if canonical_asset_id is None:
                errors.append(f"featured_assets[{index}].asset_id='{raw_asset_id}' は解決不能 ({resolve_error})。")
                continue
            if canonical_asset_id != raw_asset_id:
                logger.warning(
                    f"[Guard] Canonicalized unknown asset_id from AI: '{raw_asset_id}' -> '{canonical_asset_id}'"
                )
                asset["asset_id"] = canonical_asset_id

        if errors:
            return False, " | ".join(errors)
        return True, ""

    def __validate_evidence(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        errors: List[str] = []
        cv = result.get("causality_vector", "")
        if cv not in _VALID_CAUSALITY_VECTORS:
            errors.append(f"causality_vector='{cv}' は無効。{list(_VALID_CAUSALITY_VECTORS)} のいずれかを指定せよ。")
        ss = result.get("shield_status", "")
        if ss not in _VALID_SHIELD_STATUSES:
            errors.append(f"shield_status='{ss}' は無効。{list(_VALID_SHIELD_STATUSES)} のいずれかを指定せよ。")
        is_audit_valid, audit_error = self.__validate_portfolio_audit(result)
        if not is_audit_valid:
            errors.append(audit_error)
        if errors:
            return False, " | ".join(errors)
        return True, ""

    def __validate_portfolio_audit(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        errors: List[str] = []
        portfolio_audit = result.get("portfolio_audit")
        if portfolio_audit is not None:
            if not isinstance(portfolio_audit, dict):
                errors.append("portfolio_audit はオブジェクトでなければならない。")
            else:
                core_thesis = portfolio_audit.get("core_thesis", "")
                if core_thesis not in _VALID_CORE_THESES:
                    errors.append(f"portfolio_audit.core_thesis='{core_thesis}' は無効。{list(_VALID_CORE_THESES)} のいずれかを指定せよ。")
                cash_buffer = portfolio_audit.get("cash_buffer", "")
                if cash_buffer not in _VALID_CASH_BUFFERS:
                    errors.append(f"portfolio_audit.cash_buffer='{cash_buffer}' は無効。{list(_VALID_CASH_BUFFERS)} のいずれかを指定せよ。")
                stagnation = portfolio_audit.get("stagnation_readiness", "")
                if stagnation not in _VALID_STAGNATION_READINESS:
                    errors.append(f"portfolio_audit.stagnation_readiness='{stagnation}' は無効。{list(_VALID_STAGNATION_READINESS)} のいずれかを指定せよ。")
        if errors:
            return False, " | ".join(errors)
        return True, ""

    def __generate_exhibition_report(self, target_date: str, summary: LedgerSummary, assets: List[Position], ledger: Optional[Ledger] = None) -> Optional[Dict[str, Any]]:
        dates = self._get_context_dates(target_date)
        # 表示書式を経た値をそのまま使う。生値へ替えると parse_pct_str の丸めが
        # 外れ、テーマ判定の境界が動く。書式は View 側の定義と一致させる。
        fmt_total_diff_pct = f"{summary.total_diff_pct:+.2f}%"
        fmt_safe_ratio = f"{summary.safe_ratio_pct:.1f}%"
        fmt_total_pl = f"{summary.capital_gain_jpy:+,}"
        diff_pct = SystemUtils.parse_pct_str(fmt_total_diff_pct)
        theme, angle = self.__determine_exhibition_theme(diff_pct)

        gallery_items = []
        id_data_map: Dict[str, Dict[str, Any]] = {}
        if ledger:
            total_exposure = ledger.summary.exposure_jpy if ledger.summary.exposure_jpy > 0 else ledger.summary.total_assets_jpy

            aggregated_positions: Dict[str, Dict[str, Any]] = {}
            for p in ledger.assets:
                if p.category == "CASH": continue
                key_name = p.name.strip()

                if key_name not in aggregated_positions:
                    aggregated_positions[key_name] = {
                        "value": 0,
                        "diff_pct": p.prev_day_diff_pct,
                        "class": p.asset_class,
                        "wtd": p.wtd,
                        "id": p.id
                    }
                aggregated_positions[key_name]["value"] += p.value_jpy

            for name, d_dict in aggregated_positions.items():
                real_share = (d_dict["value"] / total_exposure * 100)
                asset_id = d_dict["id"]
                id_data_map[asset_id] = {
                    "name": name,
                    "share_pct": real_share,
                    "diff_pct": d_dict["diff_pct"],
                    "wtd": d_dict["wtd"],
                }
                if real_share >= 0.1 and d_dict['diff_pct'] != 0.0:
                    gallery_items.append(
                        f"[ID: {asset_id}] {self.__sanitize_external(name)} | Share: {real_share:.1f}% | 単日騰落: {d_dict['diff_pct']:+.2f}%"
                    )
        else:
            for a in assets:
                if a.asset_class in _CASH_ASSET_CLASSES: continue
                if a.share < 0.1: continue
                fmt_diff_pct = f"{a.prev_day_diff_pct:+.2f}%"
                gallery_items.append(f"[ID: {a.id}] {self.__sanitize_external(a.name)} | Share: {a.share:.1f}% | 単日騰落: {fmt_diff_pct}")
                if a.id not in id_data_map:
                    id_data_map[a.id] = {
                        "name": a.name,
                        "share_pct": a.share,
                        "diff_pct": SystemUtils.parse_pct_str(fmt_diff_pct),
                        "wtd": a.wtd,
                    }

        gallery_text = "\n".join(gallery_items)
        logger.info(f"[Parsing] Constructed gallery with {len(gallery_items)} items.")

        if dates["us_was_holiday"]:
            us_market_context = US_MARKET_CONTEXT_HOLIDAY.format(
                cal_label=dates["us_cal_label"],
                trading_label=dates["us_label"]
            )
            logger.info(f"[Guard] Holiday context active: {dates['us_cal_label']}")
        else:
            us_market_context = US_MARKET_CONTEXT_NORMAL.format(cal_label=dates["us_cal_label"])
            logger.info(f"[Parsing] Normal trading day context: {dates['us_cal_label']}")

        market_data_str = self.__market_fetcher.fetch_market_context(dates["us_full"])
        market_data_str = self.__sanitize_external(market_data_str)
        logger.info(f"[Acquisition] Market data injected: {market_data_str}")
        us_market_context = f"{us_market_context}\n{market_data_str}"

        _NA_STR = "保有なし (N/A)"
        if ledger:
            raw_tech, raw_metal = self.__compute_actual_evidence(ledger)
        else:
            raw_tech, raw_metal = None, None
        sys_tech_pct = f"{raw_tech:+.2f}%" if raw_tech is not None else _NA_STR
        sys_metal_pct = f"{raw_metal:+.2f}%" if raw_metal is not None else _NA_STR
        logger.info(f"[Parsing] System evidence injected: tech={sys_tech_pct}, metal={sys_metal_pct}")

        prompt = CURATOR_EXHIBITION_REPORT.format(
            jp_date=dates['jp_full'],
            theme=theme,
            angle=angle,
            us_date=dates['us_full'],
            us_market_context=us_market_context,
            total_diff_pct=fmt_total_diff_pct,
            safe_ratio=fmt_safe_ratio,
            total_return=fmt_total_pl,
            gallery_text=gallery_text,
            sys_tech_pct=sys_tech_pct,
            sys_metal_pct=sys_metal_pct
        )

        validation_error = ""
        result = None

        for attempt in range(_MAX_VALIDATION_RETRIES):
            feedback_suffix = (
                f"\n\n[VALIDATION_FEEDBACK]\n{validation_error}\n上記の検証エラーを修正し、正確な数値で再出力せよ。"
                if validation_error else ""
            )
            if attempt > 0:
                logger.warning(f"[Validation Error] Attempt {attempt + 1}/{_MAX_VALIDATION_RETRIES}: {validation_error}")
            result = self.__execute_prompt(
                prompt + feedback_suffix,
                fallback_mode="EXHIBITION",
                theme_fallback=theme
            )
            if result is None:
                break
            is_assets_valid, asset_validation_error = self.__canonicalize_featured_assets(result, id_data_map)
            if not is_assets_valid:
                validation_error = asset_validation_error
                if attempt == _MAX_VALIDATION_RETRIES - 1:
                    logger.error(f"[Validation Error] Max retries ({_MAX_VALIDATION_RETRIES}) exhausted. Skipping context report.")
                    return None
                continue
            if ledger is None or "causality_vector" not in result:
                is_valid, validation_error = self.__validate_portfolio_audit(result)
            else:
                is_valid, validation_error = self.__validate_evidence(result)
            if is_valid:
                logger.info(f"[Audit] Evidence validation passed (attempt {attempt + 1}/{_MAX_VALIDATION_RETRIES})")
                break
            if attempt == _MAX_VALIDATION_RETRIES - 1:
                logger.error(f"[Validation Error] Max retries ({_MAX_VALIDATION_RETRIES}) exhausted. Skipping context report.")
                return None

        if result:
            result["meta"] = {
                "safe_ratio": fmt_safe_ratio,
                "total_return": fmt_total_pl,
                "date_label": dates['jp_label'],
                "theme_code": theme
            }

            headline = result.get("statement_headline", "")
            body = result.get("statement_body", "")

            result["overview"] = f"{headline}\n\n{body}" if headline and body else (body or headline)
            result["theme"] = result.get("theme_title", "")
            result["implication"] = result.get("insight", "")
            result["_ledger_data"] = id_data_map

            logger.info(f"[Outcome] Curation complete: '{result['theme']}'")
            return result
        else:
            logger.error("[Outcome] Curation failed.")
            return None

    def __execute_prompt(self, prompt: str, fallback_mode: str, theme_fallback: str = "") -> Optional[Dict[str, Any]]:
        logger.info(f"[Acquisition] Sending intelligence request (Mode: {fallback_mode}, Size: {len(prompt)})")

        try:
            raw_response = self.__transporter.request_intelligence(prompt)
            logger.info(f"[Parsing] Extracting content from AI response (Length: {len(raw_response)})")

            json_content = SystemUtils.extract_json_from_response(raw_response)

            try:
                data = json.loads(json_content)

                violations = []
                all_text = [
                    data.get("theme_title", ""),
                    data.get("statement_headline", ""),
                    data.get("statement_body", ""),
                    data.get("insight", ""),
                    data.get("shield_evaluation", "")
                ]
                portfolio_audit = data.get("portfolio_audit")
                if isinstance(portfolio_audit, dict):
                    all_text.extend(str(value) for value in portfolio_audit.values())
                for asset in data.get("featured_assets", []):
                    all_text.append(asset.get("caption", ""))

                combined_text = " ".join(all_text)
                for word in CURATOR_BANNED_WORDS:
                    if word in combined_text:
                        violations.append(word)

                if violations:
                    violation_msg = f"Action Ban Violation: {violations}"
                    logger.error(f"[Audit] Censorship failed: {violation_msg}")
                    raise RuntimeError(violation_msg)

                logger.info(f"[Audit] Content integrity verified.")
                return data

            except json.JSONDecodeError as jde:
                logger.error(f"[Audit] JSON Decode Failed: {jde}")
                return None

        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.error(f"[Audit] Prompt execution exception: {e}")
            return None

