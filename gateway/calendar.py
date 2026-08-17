"""XSHG market-session classification in Asia/Shanghai time."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Optional, Protocol
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class SessionCalendar(Protocol):
    def is_session(self, day: date) -> bool:
        ...

    def next_session(self, day: date, include_day: bool = False) -> date:
        ...


class WeekdayCalendar:
    """Small deterministic calendar used by tests and explicit injection.

    Production images install and use ``exchange-calendars``' XSHG calendar.
    This test double deliberately only claims weekday knowledge and must not be
    used as the production default.
    """

    def __init__(self, holidays: Optional[set] = None) -> None:
        self.holidays = set(holidays or ())

    def is_session(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def next_session(self, day: date, include_day: bool = False) -> date:
        cursor = day if include_day else day + timedelta(days=1)
        for _ in range(370):
            if self.is_session(cursor):
                return cursor
            cursor += timedelta(days=1)
        raise RuntimeError("could not find a following weekday session")


class XSHGCalendar:
    """Holiday-aware XSHG session calendar.

    ``exchange-calendars`` supplies the exchange-specific historical schedule.
    Its pinned 4.5.6 release stops at 2025, so the maintained
    ``chinese-calendar`` release supplies the published Chinese holiday data
    for 2026. Weekends remain non-sessions even when China declares a make-up
    workday. This avoids treating an out-of-range exchange schedule as a
    successful 2026 lookup.
    """

    source = "exchange-calendars/XSHG + chinese-calendar"

    def __init__(self, backend: Optional[Any] = None) -> None:
        self._pandas = None
        self._chinese_calendar = None
        if backend is None:
            try:
                import exchange_calendars as exchange_calendars
                import pandas as pandas

                backend = exchange_calendars.get_calendar("XSHG")
                self._pandas = pandas
            except (ImportError, ModuleNotFoundError, ValueError) as exc:
                raise RuntimeError(
                    "exchange-calendars with the XSHG calendar is required"
                ) from exc
        try:
            import chinese_calendar

            self._chinese_calendar = chinese_calendar
        except ImportError as exc:
            raise RuntimeError("chinese-calendar is required for current XSHG holidays") from exc
        self._backend = backend
        if self._pandas is None:
            try:
                import pandas as pandas

                self._pandas = pandas
            except ImportError as exc:
                raise RuntimeError("pandas is required by the XSHG calendar") from exc

    def _timestamp(self, day: date) -> Any:
        return self._pandas.Timestamp(day)

    def is_session(self, day: date) -> bool:
        if day.weekday() >= 5:
            return False
        try:
            if not self._chinese_calendar.is_workday(day):
                return False
        except NotImplementedError:
            # The pinned holiday package currently publishes through 2026;
            # do not silently claim a future holiday schedule is authoritative.
            last_session = getattr(self._backend, "last_session", None)
            if last_session is None or day > last_session.date():
                raise RuntimeError(
                    "XSHG holiday data is out of range for %s" % day.isoformat()
                )
        last_session = getattr(self._backend, "last_session", None)
        if last_session is not None and day <= last_session.date():
            try:
                return bool(self._backend.is_session(self._timestamp(day)))
            except Exception:
                return False
        return True

    def next_session(self, day: date, include_day: bool = False) -> date:
        cursor = day if include_day else day + timedelta(days=1)
        for _ in range(370):
            if self.is_session(cursor):
                return cursor
            cursor += timedelta(days=1)
        raise RuntimeError("XSHG calendar returned no following session")


@dataclass(frozen=True)
class MarketSession:
    state: str
    session_date: Optional[str]
    is_trading_day: bool
    next_open_at: str

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "session_date": self.session_date,
            "is_trading_day": self.is_trading_day,
            "next_open_at": self.next_open_at,
        }


class MarketSessionClock:
    """Classify the five product-visible XSHG session states."""

    PRE_OPEN = time(9, 30)
    MORNING_CLOSE = time(11, 30)
    AFTERNOON_OPEN = time(13, 0)
    MARKET_CLOSE = time(15, 0)

    def __init__(self, calendar: Optional[SessionCalendar] = None) -> None:
        if calendar is not None:
            self.calendar = calendar
            self.calendar_source = getattr(calendar, "source", "injected")
        else:
            self.calendar = XSHGCalendar()
            self.calendar_source = XSHGCalendar.source

    @staticmethod
    def _as_shanghai(value: Optional[datetime]) -> datetime:
        if value is None:
            return datetime.now(SHANGHAI_TZ)
        if value.tzinfo is None:
            return value.replace(tzinfo=SHANGHAI_TZ)
        return value.astimezone(SHANGHAI_TZ)

    @staticmethod
    def _open_at(day: date, opening: time) -> datetime:
        return datetime.combine(day, opening, tzinfo=SHANGHAI_TZ)

    def _next_session_open(self, day: date) -> str:
        next_day = self.calendar.next_session(day, include_day=False)
        return self._open_at(next_day, self.PRE_OPEN).isoformat()

    def session_at(self, value: Optional[datetime] = None) -> MarketSession:
        now = self._as_shanghai(value)
        today = now.date()
        if not self.calendar.is_session(today):
            next_open = self._next_session_open(today)
            return MarketSession("STANDBY", None, False, next_open)

        current = now.time().replace(tzinfo=None)
        day_text = today.isoformat()
        if current < self.PRE_OPEN:
            next_open = self._open_at(today, self.PRE_OPEN).isoformat()
            return MarketSession("PRE_MARKET", day_text, True, next_open)
        if current < self.MORNING_CLOSE:
            next_open = self._open_at(today, self.AFTERNOON_OPEN).isoformat()
            return MarketSession("TRADING", day_text, True, next_open)
        if current < self.AFTERNOON_OPEN:
            next_open = self._open_at(today, self.AFTERNOON_OPEN).isoformat()
            return MarketSession("MIDDAY_BREAK", day_text, True, next_open)
        if current < self.MARKET_CLOSE:
            next_open = self._next_session_open(today)
            return MarketSession("TRADING", day_text, True, next_open)
        return MarketSession("CLOSED", day_text, True, self._next_session_open(today))

    def latest_session_on_or_before(self, value: date) -> Optional[date]:
        cursor = value
        for _ in range(370):
            if self.calendar.is_session(cursor):
                return cursor
            cursor -= timedelta(days=1)
        return None
