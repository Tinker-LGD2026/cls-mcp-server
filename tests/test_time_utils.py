"""cls_convert_time 工具的单元测试"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

import pytest

from cls_mcp_server.tools.time_utils import (
    _get_tz,
    _parse_human_readable,
    _parse_relative_time,
    cls_convert_time,
)

# 东八区时区
CST = timezone(timedelta(hours=8))


# ============================================================
# _get_tz 时区解析测试
# ============================================================

class TestGetTz:
    def test_asia_shanghai(self):
        tz = _get_tz("Asia/Shanghai")
        assert tz.utcoffset(None) == timedelta(hours=8)

    def test_utc(self):
        tz = _get_tz("UTC")
        assert tz.utcoffset(None) == timedelta(0)

    def test_us_pacific(self):
        tz = _get_tz("US/Pacific")
        assert tz.utcoffset(None) == timedelta(hours=-8)

    def test_invalid_timezone(self):
        with pytest.raises(ValueError, match="不支持的时区"):
            _get_tz("Invalid/Timezone_That_Does_Not_Exist_XYZ")


# ============================================================
# _parse_relative_time 相对时间解析测试
# ============================================================

class TestParseRelativeTime:
    def test_now(self):
        before = datetime.now(CST)
        result = _parse_relative_time("now", CST)
        after = datetime.now(CST)
        assert before <= result <= after

    def test_today(self):
        result = _parse_relative_time("today", CST)
        now = datetime.now(CST)
        assert result.year == now.year
        assert result.month == now.month
        assert result.day == now.day
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_yesterday(self):
        result = _parse_relative_time("yesterday", CST)
        expected = datetime.now(CST) - timedelta(days=1)
        assert result.year == expected.year
        assert result.month == expected.month
        assert result.day == expected.day
        assert result.hour == 0

    def test_tomorrow(self):
        result = _parse_relative_time("tomorrow", CST)
        expected = datetime.now(CST) + timedelta(days=1)
        assert result.day == expected.day
        assert result.hour == 0

    def test_yesterday_with_time(self):
        result = _parse_relative_time("yesterday 12:00:00", CST)
        expected = datetime.now(CST) - timedelta(days=1)
        assert result.day == expected.day
        assert result.hour == 12
        assert result.minute == 0
        assert result.second == 0

    def test_yesterday_with_short_time(self):
        result = _parse_relative_time("yesterday 13:30", CST)
        expected = datetime.now(CST) - timedelta(days=1)
        assert result.day == expected.day
        assert result.hour == 13
        assert result.minute == 30

    def test_today_with_time(self):
        result = _parse_relative_time("today 09:30", CST)
        now = datetime.now(CST)
        assert result.day == now.day
        assert result.hour == 9
        assert result.minute == 30

    def test_tomorrow_with_time(self):
        result = _parse_relative_time("tomorrow 08:00:00", CST)
        expected = datetime.now(CST) + timedelta(days=1)
        assert result.day == expected.day
        assert result.hour == 8

    def test_hours_ago(self):
        before = datetime.now(CST) - timedelta(hours=3, seconds=1)
        result = _parse_relative_time("3 hours ago", CST)
        after = datetime.now(CST) - timedelta(hours=3)
        assert before <= result <= after

    def test_minutes_ago(self):
        result = _parse_relative_time("30 minutes ago", CST)
        expected = datetime.now(CST) - timedelta(minutes=30)
        # 允许 2 秒误差
        assert abs((result - expected).total_seconds()) < 2

    def test_days_ago(self):
        result = _parse_relative_time("1 day ago", CST)
        expected = datetime.now(CST) - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_weeks_ago(self):
        result = _parse_relative_time("2 weeks ago", CST)
        expected = datetime.now(CST) - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 2

    def test_short_units(self):
        """测试缩写单位: h, m, s, d, w"""
        result = _parse_relative_time("1 h ago", CST)
        expected = datetime.now(CST) - timedelta(hours=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_invalid_relative(self):
        with pytest.raises(ValueError, match="无法解析相对时间"):
            _parse_relative_time("next week", CST)


# ============================================================
# _parse_human_readable 综合解析测试
# ============================================================

class TestParseHumanReadable:
    def test_absolute_datetime(self):
        result = _parse_human_readable("2026-03-25 14:30:00", CST)
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 25
        assert result.hour == 14
        assert result.minute == 30

    def test_absolute_date_only(self):
        result = _parse_human_readable("2026-03-25", CST)
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 25
        assert result.hour == 0

    def test_absolute_datetime_short(self):
        result = _parse_human_readable("2026-03-25 14:30", CST)
        assert result.hour == 14
        assert result.minute == 30

    def test_slash_format(self):
        result = _parse_human_readable("2026/03/25 14:30:00", CST)
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 25

    def test_relative_fallthrough(self):
        """相对时间也能通过 _parse_human_readable 解析"""
        result = _parse_human_readable("now", CST)
        now = datetime.now(CST)
        assert abs((result - now).total_seconds()) < 2

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="无法解析时间"):
            _parse_human_readable("not a valid time string", CST)


# ============================================================
# cls_convert_time 工具函数集成测试
# ============================================================

class TestClsConvertTime:
    def _run(self, **kwargs) -> str:
        return asyncio.get_event_loop().run_until_complete(cls_convert_time(**kwargs))

    def test_no_params(self):
        result = self._run()
        assert "❌" in result
        assert "二选一" in result

    def test_both_params(self):
        result = self._run(timestamp=1000000000000, human_readable="2026-01-01")
        assert "❌" in result
        assert "其中一个" in result

    def test_timestamp_to_readable(self):
        # 1774396800 秒 = UTC 2026-03-21 00:00:00 = CST 2026-03-25 08:00:00 (实际不对)
        # 用一个已知的时间戳来测试
        result = self._run(timestamp=1774396800000)
        assert "🕐" in result
        assert "2026-03-25 08:00:00" in result
        assert "1774396800000" in result
        assert "1774396800" in result

    def test_timestamp_seconds_auto_detect(self):
        """秒级时间戳也能正确处理"""
        result = self._run(timestamp=1774396800)
        assert "2026-03-25 08:00:00" in result

    def test_readable_to_timestamp(self):
        result = self._run(human_readable="2026-03-25 12:00:00")
        assert "🕐" in result
        assert "毫秒时间戳(ms):" in result
        assert "秒级时间戳(s):" in result

    def test_relative_time(self):
        result = self._run(human_readable="now")
        assert "🕐" in result
        assert "毫秒时间戳(ms):" in result

    def test_yesterday_time(self):
        result = self._run(human_readable="yesterday 12:00:00")
        assert "🕐" in result
        assert "12:00:00" in result

    def test_invalid_timezone(self):
        result = self._run(
            human_readable="2026-01-01",
            timezone_name="Invalid/TZ_XYZ_NOT_REAL",
        )
        assert "❌" in result

    def test_invalid_time_string(self):
        result = self._run(human_readable="this is not a time")
        assert "❌" in result

    def test_utc_timezone(self):
        result = self._run(
            human_readable="2026-03-25 00:00:00",
            timezone_name="UTC",
        )
        assert "🕐" in result
        assert "UTC" in result
        # UTC 时间戳应该比 CST 大 8 小时
        assert "2026-03-25 00:00:00" in result
