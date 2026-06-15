import datetime
from typing import Optional, Final, Dict
import jpholiday
import pandas_market_calendars as mcal
from src.lib.logger import setup_logger

logger = setup_logger(__name__)

class TimelineController:
    __REV: Final[str] = "Rev. 14"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing TimelineController")
        try:
            self.__nyse = mcal.get_calendar('NYSE')
        except Exception as e:
            logger.critical(f"[Critical] NYSE calendar unavailable: {e}. US market dates will use weekend-only fallback.")
            self.__nyse = None

    def get_target_date(self, manual_date: Optional[str] = None) -> str:
        if manual_date:
            return manual_date.replace('/', '-')
        candidate = datetime.datetime.now() - datetime.timedelta(days=1)
        while self.is_holiday(candidate.strftime("%Y-%m-%d")):
            candidate -= datetime.timedelta(days=1)
        return candidate.strftime("%Y-%m-%d")

    def get_previous_month_last_business_day(self, current_date_str: str) -> str:
        logger.info(f"[Parsing] Calculating previous month last business day for {current_date_str}")
        try:
            curr_dt = datetime.datetime.strptime(current_date_str, "%Y-%m-%d")
            first_day_of_current = curr_dt.replace(day=1)
            last_day_of_prev = first_day_of_current - datetime.timedelta(days=1)

            candidate = last_day_of_prev
            while self.is_holiday(candidate.strftime("%Y-%m-%d")):
                candidate -= datetime.timedelta(days=1)

            res = candidate.strftime("%Y-%m-%d")
            logger.info(f"[Parsing] Previous month last business day: {res}")
            return res
        except Exception as e:
            logger.error(f"[Critical] Failed to calculate previous month last business day: {e}")
            return current_date_str

    def get_previous_week_last_business_day(self, current_date_str: str) -> str:
        logger.info(f"[Parsing] Calculating previous week last business day for {current_date_str}")
        try:
            curr_dt = datetime.datetime.strptime(current_date_str, "%Y-%m-%d")
            start_of_current_week = curr_dt - datetime.timedelta(days=curr_dt.isoweekday() - 1)
            last_day_of_prev_week = start_of_current_week - datetime.timedelta(days=1)

            candidate = last_day_of_prev_week
            while self.is_holiday(candidate.strftime("%Y-%m-%d")):
                candidate -= datetime.timedelta(days=1)

            res = candidate.strftime("%Y-%m-%d")
            logger.info(f"[Parsing] Previous week last business day: {res}")
            return res
        except Exception as e:
            logger.error(f"[Critical] Failed to calculate previous week last business day: {e}")
            return current_date_str

    def get_us_market_context(self, jp_target_date: str) -> Dict[str, object]:
        logger.info(f"[Parsing] get_us_market_context: {jp_target_date}")
        try:
            target_dt = datetime.datetime.strptime(jp_target_date, "%Y-%m-%d")
            calendar_dt = target_dt - datetime.timedelta(days=1)
            calendar_date_str = calendar_dt.strftime("%Y-%m-%d")

            trading_date_str = self.determine_us_market_date(jp_target_date)
            is_holiday = (trading_date_str != calendar_date_str)

            logger.info(
                f"[Parsing] US Market Sync: calendar={calendar_date_str}, "
                f"trading={trading_date_str}, is_holiday={is_holiday}"
            )

            return {
                "trading_date": trading_date_str,
                "calendar_date": calendar_date_str,
                "is_holiday": is_holiday,
            }

        except Exception as e:
            logger.error(f"[Critical] US market context derivation failed: {e}")
            fallback_str = (
                datetime.datetime.strptime(jp_target_date, "%Y-%m-%d")
                - datetime.timedelta(days=1)
            ).strftime("%Y-%m-%d")
            return {
                "trading_date": fallback_str,
                "calendar_date": fallback_str,
                "is_holiday": False,
            }

    def determine_us_market_date(self, jp_target_date: str) -> str:
        logger.info(f"[Parsing] determine_us_market_date: {jp_target_date}")
        try:
            target_dt = datetime.datetime.strptime(jp_target_date, "%Y-%m-%d")
            candidate = target_dt - datetime.timedelta(days=1)

            if self.__nyse is not None:
                start_date = candidate - datetime.timedelta(days=7)
                schedule = self.__nyse.schedule(start_date=start_date, end_date=candidate)

                if not schedule.empty:
                    result = schedule.index[-1].strftime("%Y-%m-%d")
                    logger.info(f"[Parsing] NYSE trading date identified: {result}")
                    return result
                else:
                    logger.warning("[Parsing] No valid NYSE schedule found. Using fallback logic.")
            else:
                logger.warning("[Parsing] NYSE calendar instance missing. Using fallback logic.")

            return self._fallback_us_market_date(candidate)

        except Exception as e:
            logger.error(f"[Critical] US market date determination failed: {e}")
            base_date = datetime.datetime.strptime(jp_target_date, "%Y-%m-%d")
            return self._fallback_us_market_date(base_date - datetime.timedelta(days=1))

    def _fallback_us_market_date(self, candidate_dt: datetime.datetime) -> str:
        # Python weekday: 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
        # 祝日は考慮しない（NYSE カレンダー不使用時のフォールバック）
        if candidate_dt.weekday() == 5:  # 土曜日 -> 金曜日
            result_dt = candidate_dt - datetime.timedelta(days=1)
        elif candidate_dt.weekday() == 6:
            result_dt = candidate_dt - datetime.timedelta(days=2)
        else:
            result_dt = candidate_dt

        result = result_dt.strftime("%Y-%m-%d")
        logger.info(f"[Parsing] Fallback execution result: {result}")
        return result

    def is_holiday(self, date_str: str) -> bool:
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            res = dt.weekday() >= 5 or jpholiday.is_holiday(dt)
            return res
        except Exception as e:
            logger.error(f"[Guard] Date parsing failed in holiday check: {e}")
            return False
