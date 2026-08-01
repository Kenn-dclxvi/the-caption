import os
import re
import logging
import tempfile
from typing import Final, List, Union
from src.lib.logger import setup_logger

class SystemUtils:
    __REV: Final[str] = "Rev. 11"
    __REQUIRED_ENV_KEYS: Final[List[str]] = [
        "SMTP_USER", "SMTP_PASS", "SMTP_TO"
    ]
    
    __logger: Final[logging.Logger] = setup_logger(__name__)

    @staticmethod
    def check_env_vars() -> bool:
        missing = [k for k in SystemUtils.__REQUIRED_ENV_KEYS if not os.getenv(k)]
        
        if missing:
            SystemUtils.__logger.info(
                f"[Guard] MISSING Environment Variables: {', '.join(missing)}"
            )
            return False
            
        SystemUtils.__logger.info("[Guard] All Environment Variables Verified.")
        return True

    @staticmethod
    def get_flag(path: str) -> str:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                SystemUtils.__logger.warning(f"[Guard] Error reading flag at {path}: {e}")
        return ""

    @staticmethod
    def set_flag(path: str, val: str) -> bool:
        try:
            dir_ = os.path.dirname(os.path.abspath(path))
            os.makedirs(dir_, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dir_)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(val)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return True
        except Exception as e:
            SystemUtils.__logger.error(f"[Guard] Error writing flag to {path}: {e}")
            return False

    @staticmethod
    def parse_pct_str(pct_str: Union[str, float]) -> float:
        try:
            if isinstance(pct_str, (int, float)):
                return float(pct_str)
            
            s_val = str(pct_str).strip()
            if not s_val or s_val == "---":
                return 0.0

            clean = re.sub(r'[^\d\.\-]', '', s_val)
            result = float(clean) if clean else 0.0
            return result
        except (ValueError, TypeError) as e:
            SystemUtils.__logger.debug(f"[Guard] parse_pct_str: failed to parse '{pct_str}': {e}")
            return 0.0

    @staticmethod
    def extract_json_from_response(raw_response: str) -> str:
        """
        AI レスポンスから JSON 文字列を抽出する。
        [JSON_START]/[JSON_END] タグ → コードブロック → raw の順でフォールバック。
        制御文字（U+0000–U+0008, U+000B, U+000C, U+000E–U+001F, U+007F）を除去する。
        """
        json_content = raw_response.strip()

        tag_match = re.search(r'\[JSON_START\]([\s\S]*?)\[JSON_END\]', json_content)
        if tag_match:
            json_content = tag_match.group(1).strip()

        if "```json" in json_content:
            json_content = json_content.split("```json")[1].split("```")[0].strip()
        elif "```" in json_content:
            json_content = json_content.split("```")[1].split("```")[0].strip()

        json_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_content)
        return json_content
