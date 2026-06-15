import os
import re
import tempfile
from datetime import datetime
from typing import Dict, Any, Final, Optional, List
from src.config.settings import DATA_DIR
from src.lib.logger import setup_logger

logger = setup_logger(__name__)

class KnowledgeManager:
    __REV: Final[str] = "Rev. 10"
    __KNOWLEDGE_FILE: Final[str] = os.path.join(DATA_DIR, "knowledge_bank.md")

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing KnowledgeManager")

    def record_insight(self, date_str: str, report_data: Dict[str, Any]) -> bool:
        logger.info(f"[Parsing] record_insight: {date_str}")
        try:
            knowledge_map: Dict[str, str] = self.__load_knowledge_bank()

            if date_str in knowledge_map:
                logger.info(f"[Parsing] Overwriting existing entry: {date_str}")

            insight_data = report_data.get("insight") if isinstance(report_data.get("insight"), dict) else {}
            shield_data = report_data.get("shield_evaluation")
            if isinstance(shield_data, dict):
                shield = " / ".join(
                    str(part).strip()
                    for part in [shield_data.get("status"), shield_data.get("commentary")]
                    if str(part or "").strip()
                ) or "記録なし"
            else:
                shield = str(shield_data or "記録なし")

            theme = report_data.get("theme", "") or insight_data.get("theme", "")
            overview = (report_data.get("overview", "") or insight_data.get("analysis", "")).replace("\n", "  ")
            insight = report_data.get("implication", "") or insight_data.get("vix_vector", "")
            shield = shield.replace("\n", " ")
            display_context = report_data.get("display_context") if isinstance(report_data.get("display_context"), dict) else {}
            archive_context = report_data.get("archive_context") if isinstance(report_data.get("archive_context"), dict) else {}
            state_line = " | ".join(
                str(part).strip()
                for part in [
                    display_context.get("state") or archive_context.get("state"),
                    display_context.get("primary") or archive_context.get("primary_asset"),
                    display_context.get("policy") or archive_context.get("policy_status"),
                    display_context.get("shield") or archive_context.get("shield_status"),
                ]
                if str(part or "").strip()
            ) or "記録なし"
            archive_line = " | ".join(
                str(part).strip()
                for part in [
                    archive_context.get("causal_vector"),
                    archive_context.get("market_regime"),
                    archive_context.get("fx_effect"),
                    archive_context.get("vix_band"),
                    ",".join(archive_context.get("monthly_tags", [])) if isinstance(archive_context.get("monthly_tags"), list) else "",
                ]
                if str(part or "").strip()
            ) or "記録なし"
            archive_note = str(archive_context.get("short_note") or "").replace("\n", " ")

            new_entry = (
                f"## {date_str}\n"
                f"- **State**: {state_line}\n"
                f"- **Archive**: {archive_line}\n"
                f"- **Archive Note**: {archive_note}\n"
                f"- **Theme**: {theme}\n"
                f"- **Overview**: {overview}\n"
                f"- **Insight**: {insight}\n"
                f"- **Shield**: {shield}"
            )

            knowledge_map[date_str] = new_entry
            sorted_dates = sorted(knowledge_map.keys(), reverse=True)
            self.__write_knowledge_bank(knowledge_map, sorted_dates)

            logger.info("[Outcome] record_insight: Success")
            return True

        except Exception as e:
            logger.error(f"[Audit] record_insight error: {e}", exc_info=True)
            return False

    def extract_monthly_insights(self, year_month: str) -> List[Dict[str, str]]:
        logger.info(f"[Parsing] Extracting monthly insights for {year_month}")
        insights = []
        try:
            knowledge_map = self.__load_knowledge_bank()
            for date_key, content in knowledge_map.items():
                if date_key.startswith(year_month):
                    insights.append({"date": date_key, "content": content})

            insights.sort(key=lambda x: x["date"])
            logger.info(f"[Audit] Extracted {len(insights)} records for {year_month}")
            return insights
        except Exception as e:
            logger.error(f"[Audit] extract_monthly_insights failed: {e}")
            return []

    def extract_weekly_insights(self, year_week: str) -> List[Dict[str, str]]:
        logger.info(f"[Parsing] Extracting weekly insights for {year_week}")
        insights = []
        try:
            knowledge_map = self.__load_knowledge_bank()
            for date_key, content in knowledge_map.items():
                try:
                    dt = datetime.strptime(date_key, "%Y-%m-%d")
                except ValueError:
                    logger.warning(f"[Guard] Skipping invalid knowledge date key: {date_key}")
                    continue
                iso_year, iso_week, _ = dt.isocalendar()
                current_week = f"{iso_year}-W{iso_week:02d}"
                if current_week == year_week:
                    insights.append({"date": date_key, "content": content})

            insights.sort(key=lambda x: x["date"])
            logger.info(f"[Audit] Extracted {len(insights)} records for {year_week}")
            return insights
        except Exception as e:
            logger.error(f"[Audit] extract_weekly_insights failed: {e}")
            return []

    def __load_knowledge_bank(self) -> Dict[str, str]:
        knowledge_map: Dict[str, str] = {}
        if not os.path.exists(self.__KNOWLEDGE_FILE):
            logger.info("[Parsing] Knowledge bank not found. Starting fresh.")
            return knowledge_map

        try:
            with open(self.__KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                content = f.read()

            sections = re.split(r'\n(?=## )', content)
            for sec in sections:
                match = re.match(r'## (\d{4}-\d{2}-\d{2})', sec.strip())
                if match:
                    date_key = match.group(1)
                    try:
                        datetime.strptime(date_key, "%Y-%m-%d")
                    except ValueError:
                        logger.warning(f"[Guard] Skipping malformed date section in Knowledge Bank: {date_key}")
                        continue
                    knowledge_map[date_key] = sec.strip()

            logger.info(f"[Parsing] Loaded {len(knowledge_map)} entries from Knowledge Bank")
        except Exception as e:
            logger.error(f"[Audit] __load_knowledge_bank error: {e}", exc_info=True)

        return knowledge_map

    def __write_knowledge_bank(self, knowledge_map: Dict[str, str], sorted_dates: list) -> None:
        try:
            target_dir = os.path.dirname(os.path.abspath(self.__KNOWLEDGE_FILE))
            fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix='.md.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write("\n\n".join([knowledge_map[d] for d in sorted_dates]))
                os.replace(tmp_path, self.__KNOWLEDGE_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info(f"[Parsing] Saved {len(sorted_dates)} entries to Knowledge Bank")
        except Exception as e:
            logger.error(f"[Audit] __write_knowledge_bank error: {e}", exc_info=True)
