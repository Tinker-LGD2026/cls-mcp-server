"""参数校验 bad case 测试"""

import json
from cls_mcp_server.utils.errors import ParamValidationError, format_validation_errors
from cls_mcp_server.utils.validators import (
    is_analytics_mode,
    validate_search_log_params,
    validate_log_context_params,
    validate_log_histogram_params,
    validate_log_count_params,
)

passed = 0
failed = 0


def test(name, func, expect_field=None):
    global passed, failed
    try:
        func()
        print(f"FAIL {name}: expected ParamValidationError but none raised")
        failed += 1
    except ParamValidationError as e:
        result = json.loads(format_validation_errors(e.errors))
        assert result["success"] is False
        assert result["error_type"] == "VALIDATION_ERROR"
        assert len(result["errors"]) > 0
        for err in result["errors"]:
            for key in ["param", "value", "reason", "expected"]:
                assert key in err, f"{name}: missing key {key}"
        if expect_field:
            params = str([err["param"] for err in result["errors"]])
            assert expect_field in params, f"{name}: expected {expect_field} in {params}"
        print(f'PASS {name}: {len(result["errors"])} error(s) - {[e["param"] for e in result["errors"]]}')
        passed += 1
    except Exception as ex:
        print(f"FAIL {name}: unexpected {type(ex).__name__}: {ex}")
        failed += 1


# --- 6 个已知 bad case ---
test("search_log empty topic_id",
     lambda: validate_search_log_params("", "*", 100, 200, 10, "desc"),
     "topic_id")

test("search_log negative limit",
     lambda: validate_search_log_params("abc", "*", 100, 200, -1, "desc"),
     "limit")

test("search_log zero limit",
     lambda: validate_search_log_params("abc", "*", 100, 200, 0, "desc"),
     "limit")

test("search_log invalid sort",
     lambda: validate_search_log_params("abc", "*", 100, 200, 10, "random"),
     "sort")

test("search_log time reversed",
     lambda: validate_search_log_params("abc", "*", 200, 100, 10, "desc"),
     "start_time")

test("log_context empty topic_id",
     lambda: validate_log_context_params("", "1774537847429", "pkg1", 1, 10, 10),
     "topic_id")

# --- 额外覆盖 ---
test("log_context empty pkg_id",
     lambda: validate_log_context_params("abc", "1774537847429", "", 1, 10, 10),
     "pkg_id")

test("log_context negative prev_logs",
     lambda: validate_log_context_params("abc", "1774537847429", "pkg1", 1, -5, 10),
     "prev_logs")

test("search_log multiple errors",
     lambda: validate_search_log_params("", "", 200, 100, -1, "random"),
     "topic_id")

test("histogram negative interval",
     lambda: validate_log_histogram_params("abc", "*", 100, 200, -1000),
     "interval")

test("count empty query",
     lambda: validate_log_count_params("abc", "", 100, 200),
     "query")

# --- 正向用例（不应抛异常）---
try:
    validate_search_log_params("abc-123", "*", 100, 200, 10, "desc")
    validate_search_log_params("abc-123", "level:ERROR", 100, 200, 1000, "asc")
    validate_log_context_params("abc-123", "1774537847429", "pkg1", 1, 10, 10)
    validate_log_histogram_params("abc-123", "*", 100, 200, None)
    validate_log_histogram_params("abc-123", "*", 100, 200, 60000)
    validate_log_count_params("abc-123", "*", 100, 200)
    print("PASS normal cases: all passed without error")
    passed += 1
except Exception as ex:
    print(f"FAIL normal cases: {type(ex).__name__}: {ex}")
    failed += 1

# --- 验证多错误批量返回 ---
try:
    validate_search_log_params("", "", 200, 100, -1, "random")
except ParamValidationError as e:
    result = json.loads(format_validation_errors(e.errors))
    count = len(result["errors"])
    if count >= 4:
        print(f"PASS batch errors: {count} errors returned in one response")
        passed += 1
    else:
        print(f"FAIL batch errors: expected >= 4 errors, got {count}")
        failed += 1

# --- 分析模式：limit 和 sort 不校验 ---
print("\n--- 分析模式测试（query 含 |，limit/sort 跳过校验）---")

# is_analytics_mode 函数测试
assert is_analytics_mode("* | SELECT COUNT(*) AS cnt") is True
assert is_analytics_mode("level:ERROR | SELECT service, COUNT(*) AS cnt GROUP BY service") is True
assert is_analytics_mode("level:ERROR") is False
assert is_analytics_mode("*") is False
assert is_analytics_mode("") is False
print("PASS is_analytics_mode: 所有断言通过")
passed += 1

# 分析模式下，limit=-1, sort="random" 不应报错
try:
    validate_search_log_params("abc-123", "* | SELECT COUNT(*) AS cnt", 100, 200, -1, "random")
    print("PASS analytics mode: limit=-1 sort=random 不报错")
    passed += 1
except ParamValidationError as e:
    result = json.loads(format_validation_errors(e.errors))
    params = [err["param"] for err in result["errors"]]
    print(f"FAIL analytics mode: 分析模式不应校验 limit/sort，但报了: {params}")
    failed += 1

# 分析模式下，limit=0 不应报错
try:
    validate_search_log_params("abc-123", "* | SELECT status, COUNT(*) GROUP BY status", 100, 200, 0, "desc")
    print("PASS analytics mode: limit=0 不报错")
    passed += 1
except ParamValidationError:
    print("FAIL analytics mode: limit=0 在分析模式下不应报错")
    failed += 1

# 分析模式下，limit=99999 不应报错
try:
    validate_search_log_params("abc-123", "* | SELECT COUNT(*) AS cnt", 100, 200, 99999, "xyz")
    print("PASS analytics mode: limit=99999 sort=xyz 不报错")
    passed += 1
except ParamValidationError:
    print("FAIL analytics mode: limit=99999 sort=xyz 在分析模式下不应报错")
    failed += 1

# 分析模式下，topic_id 空和时间逆序仍然要校验
test("analytics mode empty topic_id still fails",
     lambda: validate_search_log_params("", "* | SELECT COUNT(*) AS cnt", 100, 200, 10, "desc"),
     "topic_id")

test("analytics mode time reversed still fails",
     lambda: validate_search_log_params("abc-123", "* | SELECT COUNT(*) AS cnt", 200, 100, 10, "desc"),
     "start_time")

# 检索模式下，limit 和 sort 仍然校验
test("search mode limit=-1 still fails",
     lambda: validate_search_log_params("abc-123", "level:ERROR", 100, 200, -1, "desc"),
     "limit")

test("search mode sort=random still fails",
     lambda: validate_search_log_params("abc-123", "*", 100, 200, 10, "random"),
     "sort")

print(f"\n=== Results: {passed} passed, {failed} failed ===")
