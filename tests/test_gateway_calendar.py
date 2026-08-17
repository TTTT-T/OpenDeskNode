from datetime import date, datetime
import unittest
from unittest.mock import patch

from gateway.calendar import MarketSessionClock, SHANGHAI_TZ, WeekdayCalendar


class GatewayCalendarTests(unittest.TestCase):
    def setUp(self):
        self.calendar = WeekdayCalendar({date(2026, 10, 1)})
        self.clock = MarketSessionClock(self.calendar)

    def at(self, value):
        return datetime.fromisoformat(value).replace(tzinfo=SHANGHAI_TZ)

    def test_weekday_session_boundaries(self):
        pre = self.clock.session_at(self.at("2026-08-17T09:29:59"))
        self.assertEqual(pre.state, "PRE_MARKET")
        self.assertEqual(pre.next_open_at, "2026-08-17T09:30:00+08:00")

        morning = self.clock.session_at(self.at("2026-08-17T10:00:00"))
        self.assertEqual(morning.state, "TRADING")
        self.assertEqual(morning.next_open_at, "2026-08-17T13:00:00+08:00")

        lunch = self.clock.session_at(self.at("2026-08-17T11:30:00"))
        self.assertEqual(lunch.state, "MIDDAY_BREAK")
        self.assertEqual(lunch.next_open_at, "2026-08-17T13:00:00+08:00")

        afternoon = self.clock.session_at(self.at("2026-08-17T13:00:00"))
        self.assertEqual(afternoon.state, "TRADING")
        self.assertEqual(afternoon.next_open_at, "2026-08-18T09:30:00+08:00")

        closed = self.clock.session_at(self.at("2026-08-17T15:00:00"))
        self.assertEqual(closed.state, "CLOSED")
        self.assertEqual(closed.next_open_at, "2026-08-18T09:30:00+08:00")

    def test_weekend_and_holiday_are_standby(self):
        weekend = self.clock.session_at(self.at("2026-08-16T12:00:00"))
        self.assertEqual(weekend.state, "STANDBY")
        self.assertEqual(weekend.next_open_at, "2026-08-17T09:30:00+08:00")
        holiday = self.clock.session_at(self.at("2026-10-01T12:00:00"))
        self.assertEqual(holiday.state, "STANDBY")
        self.assertEqual(holiday.next_open_at, "2026-10-02T09:30:00+08:00")

    def test_default_xshg_backend_handles_2026_dates_when_installed(self):
        clock = MarketSessionClock()
        session = clock.session_at(self.at("2026-08-17T10:00:00"))
        self.assertEqual(session.state, "TRADING")
        holiday = clock.session_at(self.at("2026-10-01T10:00:00"))
        self.assertEqual(holiday.state, "STANDBY")

    def test_default_calendar_dependency_failure_is_explicit(self):
        with patch(
            "gateway.calendar.XSHGCalendar",
            side_effect=RuntimeError("missing XSHG dependency"),
        ):
            with self.assertRaisesRegex(RuntimeError, "missing XSHG dependency"):
                MarketSessionClock()


if __name__ == "__main__":
    unittest.main()
