import json
import re
from typing import Optional, Dict, Any, List, Final
from src.lib.logger import setup_logger
from src.infra.llm_transporter import LlmTransporter
from src.config.prompts import WEEKLY_CHRONICLE_REPORT, CURATOR_BANNED_WORDS
from src.app.renderer.view_models import SummaryViewModel

logger = setup_logger(__name__)

class WeeklyCurator:
    __REV: Final[str] = "Rev. 1"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing WeeklyCurator")
        self.__transporter = LlmTransporter()

    def generate_weekly_chronicle(self, year_week: str, summary_vm: SummaryViewModel, insights: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        logger.info(f"[Parsing] Generating Weekly Chronicle for {year_week} with {len(insights)} records")

        if len(insights) < 3:
            logger.warning(f"[Guard] The Void engaged: Only {len(insights)} records found for {year_week} (< 3). AI generation skipped.")
            return {}

        insight_stream_text = ""
        for record in insights:
            insight_stream_text += f"[{record['date']}]\n{record['content']}\n\n"

        prompt = WEEKLY_CHRONICLE_REPORT.format(
            year_week=year_week,
            insight_stream=insight_stream_text,
            safe_ratio=summary_vm.fmt_safe_ratio
        )

        return self.__execute_prompt(prompt)

    def __execute_prompt(self, prompt: str) -> Optional[Dict[str, Any]]:
        logger.info(f"[Acquisition] Executing weekly prompt (Size: {len(prompt)}):\n{prompt}")

        try:
            raw_response = self.__transporter.request_intelligence(prompt)
            logger.info(f"[Parsing] Received full AI response:\n{raw_response}")

            json_content = ""
            tag_match = re.search(r'\[JSON_START\]([\s\S]*?)\[JSON_END\]', raw_response)
            if tag_match:
                json_content = tag_match.group(1).strip()
            else:
                json_content = raw_response.strip()

            if "```json" in json_content:
                json_content = json_content.split("```json")[1].split("```")[0].strip()
            elif "```" in json_content:
                json_content = json_content.split("```")[1].split("```")[0].strip()

            json_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_content)

            try:
                data = json.loads(json_content)

                violations = []
                all_text = [
                    data.get("theme_title", ""),
                    data.get("chronicle_headline", ""),
                    data.get("chronicle_body", ""),
                    data.get("shield_review", "")
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
