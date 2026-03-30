# CLS CQL 检索分析语法 API 参考手册

> CQL (CLS Query Language) 是腾讯云日志服务（CLS）自研的检索分析语法，推荐使用此语法进行日志的检索与数据分析（API 参数 `SyntaxRule=1`）。
> 语句结构：`[检索条件] | [SQL 分析语句]`。检索条件用于过滤日志，SQL 用于对过滤后的结果进行统计分析。

---

## 1. CQL 检索语法（管道符 `|` 左侧）

如果只需检索日志不需要分析，可省略 `|` 及之后的 SQL 语句。如果对全量数据分析，左侧可使用 `*`。

### 1.1 基础检索语法

| 语法 | 说明 | 示例 |
|------|------|------|
| `key:value` | 键值检索，查询字段值中包含 value 的日志 | `level:ERROR` |
| `value` | 全文检索，查询全文包含 value 的日志 | `timeout` |
| `AND` | 逻辑与（不区分大小写） | `level:ERROR AND pid:1234` |
| `OR` | 逻辑或（不区分大小写） | `level:ERROR OR level:WARNING` |
| `NOT` | 逻辑非（不区分大小写） | `level:ERROR NOT pid:1234` |
| `()` | 逻辑分组控制优先级（AND 优先级最高）| `level:(ERROR OR WARNING) AND pid:1234` |
| `"..."` 或 `'...'` | 短语检索，精确匹配词组且顺序不变 | `name:"john Smith"` |
| `*` | 模糊匹配（支持后缀，**不支持前缀模糊**） | `host:www.test*.com` |
| `>`, `>=`, `<`, `<=` | 数值范围匹配 | `status:>=400` |
| `key:*` | 字段存在性判断（存在该字段） | `user_id:*` |
| `key:""` | 字段存在但值为空 | `error_msg:""` |

### 1.2 检索规则边界
- **分词默认关系**：CQL 中多个独立的分词默认为 **AND** 关系（如检索 `a b` 等价于 `a AND b`）。
- **短语内通配符**：CQL 支持在双引号短语中使用通配符（如 `filepath:"/var/log/*.log"`）。

---

## 2. SQL 分析引擎边界限制（管道符 `|` 右侧）

SQL 部分基于 **Trino/Presto** 语法引擎。默认返回 100 行，最大可返回 100 万行（需使用 LIMIT 指定）。

### 2.1 明确支持的能力
- `SELECT`, `WHERE`, `GROUP BY`, `ORDER BY`, `HAVING`, `LIMIT`
- **嵌套子查询**：支持作为数据源（如 `SELECT * FROM (SELECT ...)`）

### 2.2 明确不支持的能力（硬性限制，必定报错）
- **不支持 `JOIN` 操作**：仅支持单日志主题查询。
- **不支持 `UNION` 操作**。
- **不支持相关子查询回表过滤**：如不支持 `WHERE id IN (SELECT id FROM ...)`。
- **不需要编写 `FROM` 子句**：最外层 SQL 默认从管道符左侧检索结果中取数，直接写 `SELECT` 即可。

### 2.3 引号与转义规则
- **字符串**：必须使用单引号 `'value'`。若内部包含单引号，用两个单引号转义 `'it''s ok'`。
- **字段名**：普通字段直接写。若字段名包含特殊字符（如 `-`、`.`）或与 SQL 保留字冲突（如 `select`），**必须使用双引号** `"user-agent"`。

---

## 3. 时区规则与时间处理（高频考点）

CLS 的时间函数具有严格的时区行为划分：

| 场景 | 时区行为 | 说明 |
|------|---------|------|
| `histogram(__TIMESTAMP__, ...)`<br>`time_series(__TIMESTAMP__, ...)` | **自动 UTC+8** | 传入 `__TIMESTAMP__`（毫秒级 bigint），自动按北京时间分桶补全。 |
| 其他标准 Trino 日期时间函数<br>(`date_trunc`, `date_format`, `extract`) | **默认 UTC+0** | 如果使用 `cast(__TIMESTAMP__ as timestamp)`，结果为 UTC+0，**需要手动加 8 小时**。 |

**安全转换示例**：
```sql
-- 将 __TIMESTAMP__ 转为北京时间的 timestamp
cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR

-- 格式化为北京时间字符串
date_format(cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR, '%Y-%m-%d %H:%i:%s')
```

---

## 4. CLS 专属扩展函数

### 4.1 histogram (时间分桶)
将时间按指定间隔对齐，常用于按时间聚合统计。
- **语法**：`histogram(__TIMESTAMP__, interval <N> <unit>)`
- **Unit 支持**：`second`, `minute`, `hour`, `day`, `month`, `year`
- **示例**：
  ```sql
  * | SELECT histogram(__TIMESTAMP__, interval 5 minute) as t, COUNT(*) as cnt GROUP BY t ORDER BY t
  ```

### 4.2 time_series (时序补全)
类似 `histogram`，但在缺少数据的区间会自动填充默认值，确保时间序列连续。
- **语法**：`time_series(__TIMESTAMP__, '<interval>', '<format>', '<default_value>')`
- **参数要求**：
  - `interval`：字符串，如 `'1m'`, `'5m'`, `'1h'`, `'1d'`。
  - `format`：输出时间格式，如 `'%Y-%m-%d %H:%i:%s'`（分钟必须用 `%i`）。
  - `default_value`：缺失值填充，支持 `'0'`, `'null'`, `'last'` (沿用上一个值), `'next'`, `'avg'`。
- **硬性约束**：**必须同时使用 `GROUP BY` 和 `ORDER BY`**，且 `ORDER BY` **仅支持升序**。
- **示例**：
  ```sql
  * | SELECT time_series(__TIMESTAMP__, '1h', '%Y-%m-%d %H:%i:%s', '0') as t, COUNT(*) as cnt GROUP BY t ORDER BY t
  ```

### 4.3 compare (同环比)
将当前时间范围的聚合结果与历史周期对比。返回值是一个基于 1 起始的 JSON 数组。
- **语法**：`compare(<aggregate_expression>, <offset_seconds>)`
- **返回值**：`[当前值, offset秒前的值, 当前值/offset秒前的值]`
- **硬性约束（AST 宏重写限制）**：如果要在查询中输出其他维度列并分组计算同环比（如 `GROUP BY province, time`），引擎会报错失败。`compare` 函数在包含时间趋势时，**仅支持以 time 作为唯一分组维度**。
- **示例**（日环比趋势）：
  ```sql
  * | SELECT compare[1] AS today, compare[2] AS yesterday, time
      FROM (
        SELECT compare(PV, 86400, time) AS compare, time
        FROM (
          SELECT count(*) AS PV, histogram(__TIMESTAMP__, interval 5 minute) AS time
          GROUP BY time
        )
      )
  ```

---

## 5. 内置函数库（完全支持）

CLS 引擎完全兼容以下 Trino 标准函数及 CLS 特色提取函数。Agent 在处理复杂文本时应首选以下函数。

### 5.1 IP 地理函数
**入参均要求 varchar 类型的 IPv4/IPv6 地址**。内网 IP 返回值为空或 NULL。
- `ip_to_country(ip)`：返回国家名称
- `ip_to_province(ip)`：返回省份名称
- `ip_to_city(ip)`：返回城市名称
- `ip_to_provider(ip)`：返回运营商名称
- `ip_to_domain(ip)`：判断内外网，返回 `'intranet'`（内网）、`'internet'`（外网）或 `'invalid'`（非法）
- 网段计算：`ip_prefix(ip, bits)`, `ip_subnet_min(ip, bits)`, `ip_subnet_max(ip, bits)`, `is_subnet_of(ip, cidr)`

### 5.2 IP 威胁情报函数
- `ip_threat(ip)`：判断是否为恶意 IP，返回布尔或状态字符串
- `ip_threat_tags(ip)`：提取恶意 IP 的威胁标签数组
- `ip_threat_detail(ip)`：返回威胁情报详情的 JSON 字符串

### 5.3 JSON 函数
- `json_extract(json_string, json_path)`：提取 JSON 并返回 JSON 类型
- `json_extract_scalar(json_string, json_path)`：提取并返回 varchar 标量值（常用于字符串或数值提取）
  - 示例：`json_extract_scalar(body, '$.user.name')`

### 5.4 URL 函数
- `url_extract_host(url)`：提取 URL 中的域名
- `url_extract_path(url)`：提取 URL 中的路径
- `url_extract_parameter(url, param_name)`：提取 URL 的指定 Query 参数
- `url_extract_port(url)` / `url_extract_protocol(url)` / `url_extract_query(url)`

### 5.5 类型转换函数
- `cast(value AS type)`：强制转换，若失败会导致整个查询中断报错。
- `try_cast(value AS type)`：安全转换，若失败返回 NULL，**强烈推荐用于日志脏数据提取**。

### 5.6 日期时间函数
- `from_unixtime(unixtime)`：秒级 Unix 时间戳转 timestamp (UTC+0)。
  - **注意**：`__TIMESTAMP__` 为毫秒，需写为 `from_unixtime(__TIMESTAMP__/1000)`。
  - 带时区转换（推荐）：`from_unixtime(__TIMESTAMP__/1000, 'Asia/Shanghai')`
- `date_parse(string, format)`：字符串转 timestamp
- `date_trunc(unit, timestamp)`：截断时间（支持 second/minute/hour/day/month/year）
- `date_add(unit, value, timestamp)` / `date_diff(unit, timestamp1, timestamp2)`
- `extract(field FROM timestamp)` 或快捷函数 `hour(timestamp)` / `minute(timestamp)`

### 5.7 字符串与正则函数
- `concat(str1, str2, ...)`：字符串拼接
- `split(string, delimiter)`：字符串分割，返回数组
- `substr(string, start, length)`：截取字符串（索引从 1 开始）
- `replace(string, search, replace)`：字符串替换
- `regexp_like(string, pattern)`：正则匹配（返回 boolean）
- `regexp_extract(string, pattern, group)`：正则捕获提取
- `regexp_replace(string, pattern, replacement)`：正则替换

### 5.8 估算与聚合函数
- 基础聚合：`count(*)`, `sum(x)`, `avg(x)`, `max(x)`, `min(x)`
- `max_by(x, y)` / `min_by(x, y)`：返回 y 最大/最小时对应的 x 值
- `array_agg(x)`：聚合成数组
- `APPROX_DISTINCT(x)`：近似去重计数（性能远优于 COUNT(DISTINCT)）
- `APPROX_PERCENTILE(x, percentage)`：近似计算百分位数（percentage 范围 0.0~1.0）

### 5.9 条件控制
- `IF(condition, true_value, false_value)`
- `COALESCE(value1, value2, ...)`：返回首个非 NULL 值
- `CASE WHEN ... THEN ... ELSE ... END`

---

## 6. 内置系统字段
查询时可直接引用的隐藏字段：
- `__TIMESTAMP__`：日志采集时间（bigint，毫秒级 Unix 时间戳）
- `__SOURCE__`：日志来源标识（varchar，一般为 IP）
- `__FILENAME__`：采集日志的物理文件路径（varchar）
