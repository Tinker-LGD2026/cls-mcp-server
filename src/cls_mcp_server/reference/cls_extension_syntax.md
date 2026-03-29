# CLS CQL 检索分析语法完整参考

> CQL (CLS Query Language) 是腾讯云日志服务 CLS 自研的检索分析语法。
> 语句结构为：`[检索条件] | [SQL 分析语句]`。检索条件用于过滤日志，SQL 用于统计分析。
> CQL 相比 Lucene 语法更简便、特殊字符限制更少，是 CLS 推荐的默认语法（SyntaxRule=1）。

---

## 1. CQL 检索语法

检索条件位于管道符 `|` 左侧，用于过滤日志。如果为空或 `*`，代表查询所有日志。
如果不需要 SQL 统计分析，可省略 `|` 及其后的 SQL 语句。

### 1.1 基础语法

| 语法 | 说明 | 示例 |
|------|------|------|
| `key:value` | 键值检索，查询字段值中包含 value 的日志 | `level:ERROR` |
| `value` | 全文检索，查询日志全文中包含 value 的日志 | `ERROR` |
| `AND` | "与"逻辑操作符，**不区分大小写** | `level:ERROR AND pid:1234` |
| `OR` | "或"逻辑操作符，不区分大小写 | `level:ERROR OR level:WARNING` |
| `NOT` | "非"逻辑操作符，不区分大小写 | `level:ERROR NOT pid:1234` |
| `()` | 逻辑分组，控制优先级（AND 优先级高于 OR） | `level:(ERROR OR WARNING) AND pid:1234` |
| `"..."` | 短语检索，日志需包含完整短语且顺序不变 | `name:"john Smith"` |
| `'...'` | 短语检索，功能同 `""`，避免内部双引号转义 | `body:'user_name:"bob"'` |
| `*` | 模糊匹配，匹配零到多个字符（**不支持前缀模糊**如 `*test`） | `host:www.test*.com` |
| `>`, `>=`, `<`, `<=` | 数值范围操作符 | `status:>400`、`latency:>=1000` |
| `=` | 等于操作符（数值） | `status:=200` |
| `\\` | 转义特殊字符（空格、`:`、`*` 等） | `body:user_name\\:bob` |

### 1.2 特殊检索方式

- **字段存在性检查**：
  - `key:*` — 查询字段存在的日志
  - `key:""` — 查询字段存在但值为空的日志
- **短语检索中的通配符**：CQL 支持在短语中使用通配符（Lucene 不支持），如 `filepath:"/var/log/acc*.log"`
- **分词默认行为**：CQL 中多个分词默认为 **AND** 关系（Lucene 默认为 OR），更符合直觉
  - 例：检索 `/book/user/login` 在 CQL 中等价于 `book AND user AND login`

### 1.3 CQL 与 Lucene 语法的核心区别

| 功能 | CQL | Lucene |
|------|-----|--------|
| 逻辑操作符大小写 | **不区分**（AND/and 均可） | **仅大写**（小写视为普通文本） |
| 特殊符号转义 | 需转义的符号**较少** | 需转义的符号较多 |
| 分词默认关系 | **AND**（更符合直觉） | **OR** |
| 短语中通配符 | **支持** | 不支持 |
| 数值范围 | `status:>=400 AND status:<=499` | `status:[400 TO 499]` |
| 字段存在性 | `key:*` | `_exists_:key` |

> ⚠️ CQL 和 Lucene 在 API 请求中通过 `SyntaxRule` 参数区分：`SyntaxRule=1` 为 CQL（推荐），`SyntaxRule=0` 为 Lucene。

---

## 2. 管道符语法 `|`

CLS 使用管道符将 CQL 检索条件与 SQL 分析语句连接。

```
[CQL检索条件] | [SQL分析语句]
```

### 示例

```sql
-- 在 level:ERROR 的日志中做 SQL 分析
level:ERROR | SELECT status, COUNT(*) AS cnt GROUP BY status ORDER BY cnt DESC

-- 全量日志分析（* 表示匹配所有）
* | SELECT COUNT(*) AS total
```

### 注意
- 管道符 `|` 左侧为 CQL 检索语法，右侧为标准 SQL
- 右侧 SQL 中**不需要写 FROM 子句**，默认从检索结果中分析
- 如果不需要检索过滤，左侧用 `*` 表示匹配所有日志
- SQL 语句**不需要分号 `;` 结尾**
- 如果只需要检索日志（不需要聚合分析），只写 CQL 检索部分，不需要管道符和 SQL

---

## 3. SQL 分析前提条件与限制

### 前提条件
1. **标准存储**：日志必须接入**标准存储**，低频存储不支持 SQL 分析
2. **键值索引 + 统计**：字段需同时开启**键值索引**和**统计**功能，否则无法在 SQL 中使用该字段
3. **日志结构化**：采集日志时必须按字段提取（即日志结构化）

### 使用限制
- **默认返回 100 行**，最大支持 **100 万行**，需使用 `LIMIT` 指定
- 查询语句最大 **10KB**
- SQL 部分基于 **Trino/Presto** 语法

### 引号规则
- **字符串值必须用单引号** `''`：`'hello'`、`'Asia/Shanghai'`
- **双引号用于字段名**（当字段名包含特殊字符或与保留字冲突时）：`"select"`、`"user-agent"`
- **无引号**：直接引用普通字段名
- 字符串中包含单引号时，用两个单引号转义：`'it''s ok'`

### 支持的 SQL 语法
- `SELECT`、`WHERE`、`GROUP BY`、`ORDER BY`、`LIMIT`、`HAVING`
- **嵌套子查询**：支持（用于对统计结果进行二次分析）
- **JOIN**：不支持
- **UNION**：不支持

---

## 4. 时区规则（⚠️ 高频踩坑点）

CLS 中不同函数的时区行为不一致，这是最常见的错误来源。

### 核心规则

| 场景 | 时区行为 | 说明 |
|------|---------|------|
| `histogram(__TIMESTAMP__, interval ...)` | **自动 UTC+8** | 传入 LONG 型（毫秒时间戳），结果直接是北京时间 |
| `time_series(__TIMESTAMP__, ...)` | **自动 UTC+8** | 同上，传入 LONG 型自动转北京时间 |
| `histogram(cast(__TIMESTAMP__ as timestamp), interval ...)` | 要求输入 **UTC+0** | cast 转出的 TIMESTAMP 是 UTC+0，直接传入即可 |
| `time_series(cast(__TIMESTAMP__ as timestamp), ...)` | 要求输入 **UTC+0** | 同上 |
| `date_trunc`、`date_format`、`from_unixtime`（无时区参数）等 | **UTC+0** | 所有其他日期时间函数默认 UTC+0 |

### 推荐写法

```sql
-- ✅ 最简写法：直接传 LONG 型（__TIMESTAMP__），自动 UTC+8
* | SELECT histogram(__TIMESTAMP__, interval 1 hour) as t, COUNT(*) as cnt
  GROUP BY t ORDER BY t

-- ✅ TIMESTAMP 写法：cast 结果是 UTC+0，histogram/time_series 能正确处理
* | SELECT histogram(cast(__TIMESTAMP__ as timestamp), interval 1 hour) as t,
         COUNT(*) as cnt
  GROUP BY t ORDER BY t

-- ⚠️ 非 histogram/time_series 的函数需手动加时区偏移
-- 方法1：from_unixtime 指定时区（推荐）
* | SELECT from_unixtime(__TIMESTAMP__/1000, 'Asia/Shanghai') as bj_time

-- 方法2：手动加 8 小时（毫秒）
* | SELECT cast(__TIMESTAMP__ + 8*60*60*1000 as timestamp) as bj_time

-- 方法3：用 INTERVAL 加 8 小时
* | SELECT cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR as bj_time
```

### 常见错误

```sql
-- ❌ 错误：date_format 默认 UTC+0，结果比北京时间少 8 小时
* | SELECT date_format(cast(__TIMESTAMP__ as timestamp), '%Y-%m-%d %H:00') as hour

-- ✅ 正确：先加 8 小时偏移
* | SELECT date_format(cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR, '%Y-%m-%d %H:00') as hour

-- ❌ 错误：date_trunc 默认 UTC+0
* | SELECT date_trunc('hour', cast(__TIMESTAMP__ as timestamp)) as hour

-- ✅ 正确
* | SELECT date_trunc('hour', cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR) as hour
```

### TIMESTAMP 类型输入 histogram/time_series 的时区要求

当 histogram/time_series 接收 TIMESTAMP 类型时，该时间表达式**必须为 UTC+0**。如果原始数据是字符串格式的北京时间，需要先减去 8 小时：

```sql
-- 字符串北京时间转 UTC+0 后传给 histogram
* | SELECT histogram(date_parse(time_str, '%Y-%m-%d %H:%i:%s') - INTERVAL 8 HOUR, interval 1 hour) as t,
         COUNT(*) as cnt
  GROUP BY t ORDER BY t
```

---

## 5. histogram — 时间分桶函数（CLS 重载版）

标准 Trino 的 `histogram` 是聚合函数（构建 MAP），CLS 将其重载为**时间分桶**函数。

### 语法

```sql
-- LONG 型写法（推荐，自动 UTC+8）
histogram(__TIMESTAMP__, interval <N> <unit>)

-- TIMESTAMP 型写法
histogram(cast(__TIMESTAMP__ as timestamp), interval <N> <unit>)
```

### 参数
- **第一个参数**：时间列
  - LONG 型（`__TIMESTAMP__`）：毫秒级 Unix 时间戳，自动按 UTC+8 处理
  - TIMESTAMP 型（`cast(__TIMESTAMP__ as timestamp)`）：要求 UTC+0 时区
- **第二个参数**：分桶间隔，格式为 `interval N unit`
  - 支持的 unit：`second`、`minute`、`hour`、`day`、`month`、`year`
- **`${__interval}`**：仅控制台可用的动态间隔变量，API 调用中不支持

### 示例

```sql
-- ✅ 推荐写法：LONG 型，自动 UTC+8
* | SELECT histogram(__TIMESTAMP__, interval 1 hour) as t,
         COUNT(*) as cnt
  GROUP BY t ORDER BY t

-- 按 5 分钟分桶统计错误数
level:ERROR | SELECT histogram(__TIMESTAMP__, interval 5 minute) as t,
                    COUNT(*) as cnt
             GROUP BY t ORDER BY t

-- TIMESTAMP 型写法（也正确）
* | SELECT histogram(cast(__TIMESTAMP__ as timestamp), interval 1 day) as t,
         COUNT(*) as cnt
  GROUP BY t ORDER BY t
```

---

## 6. time_series — 时序补全函数

在时间维度聚合时，如果某个时间段没有数据，`histogram` 不会返回该时间点。
`time_series` 会自动补全缺失的时间点，使时间序列连续，适合绘图场景。

### 语法

```sql
-- LONG 型写法（推荐，自动 UTC+8）
time_series(__TIMESTAMP__, '<interval>', '<format>', '<default_value>')

-- TIMESTAMP 型写法
time_series(cast(__TIMESTAMP__ as timestamp), '<interval>', '<format>', '<default_value>')
```

### 参数
- **第一个参数**：时间列（LONG 型或 TIMESTAMP 型，时区规则同 histogram）
- **第二个参数**：时间间隔，字符串格式
  - `'30s'`（秒）、`'1m'`/`'5m'`（分钟）、`'1h'`（小时）、`'1d'`（天）
- **第三个参数**：输出时间格式，如 `'%Y-%m-%d %H:%i:%s'`
  - ⚠️ 分钟格式符是 **`%i`**，不是 `%M`（`%M` 是英文月份名）
- **第四个参数**：缺失时间点的填充值
  - `'0'`：填充 0
  - `'null'`：填充 null
  - `'last'`：填充上一个时间点的值
  - `'next'`：填充下一个时间点的值
  - `'avg'`：填充前后两个时间点的平均值

### 严格语法规则
1. **必须搭配 `GROUP BY`** 使用
2. **必须搭配 `ORDER BY`** 使用
3. **ORDER BY 不支持 `DESC`**（只能升序）

### 示例

```sql
-- ✅ 推荐写法：LONG 型，每 5 分钟统计，缺失补 0
* | SELECT time_series(__TIMESTAMP__, '5m', '%Y-%m-%d %H:%i:%s', '0') as time,
         COUNT(*) as cnt
  GROUP BY time
  ORDER BY time

-- 每小时统计错误数，缺失补 0
level:ERROR | SELECT time_series(__TIMESTAMP__, '1h', '%Y-%m-%d %H:%i:%s', '0') as time,
                    COUNT(*) as cnt
             GROUP BY time
             ORDER BY time

-- 使用 last 填充（适合监控指标，缺失值沿用前值）
* | SELECT time_series(__TIMESTAMP__, '1m', '%Y-%m-%d %H:%i:%s', 'last') as time,
         AVG(cpu_usage) as avg_cpu
  GROUP BY time
  ORDER BY time
```

---

## 7. compare — 同环比函数

用于将当前时间范围的聚合结果与历史同期对比（同比/环比）。

### 语法

```sql
-- 基础对比：单周期
compare(<aggregate_expression>, <offset_seconds>)

-- 基础对比：多周期
compare(<aggregate_expression>, <offset1_seconds>, <offset2_seconds>, ...)

-- 趋势对比：含时间列（用于时序图对比）
compare(<aggregate_expression>, <offset_seconds>, <time_column>)

-- 趋势对比：多周期含时间列
compare(<aggregate_expression>, <offset1>, <offset2>, ..., <time_column>)
```

### 参数
- **aggregate_expression**：聚合表达式，值必须为 `double` 或 `long` 类型，如 `count(*)`、`avg(latency)`
- **offset_seconds**：时间偏移量（秒），支持多个
  - `3600`：1 小时前
  - `86400`：1 天前（日环比）
  - `604800`：7 天前（周同比）
  - `2592000`：30 天前（月同比）
  - `31622400`：1 年前（年同比）
- **time_column**：时间列（`timestamp` 类型），用于趋势对比，通常由 `histogram` 或 `time_series` 生成

### 返回值
返回一个 **JSON 数组**：
- `compare(x, n)` → `[当前值, n秒前的值, 当前值/n秒前的值]`
- `compare(x, n1, n2)` → `[当前值, n1秒前的值, n2秒前的值, 比率1, 比率2]`

数组下标从 **1** 开始（CLS 特有，非标准 SQL 的 0 起始）。

### 展开数组结果

```sql
-- 展开日环比结果为独立列（需使用子查询）
* | SELECT compare[1] AS today, compare[2] AS yesterday, compare[3] AS ratio
  FROM (
    SELECT compare(count(*), 86400) AS compare
    FROM (
      SELECT count(*) AS PV
    )
  )
```

### 趋势对比示例

```sql
-- 今天 vs 昨天，每 5 分钟一个点的对比趋势
* | SELECT compare[1] AS today, compare[2] AS yesterday, time
  FROM (
    SELECT compare(PV, 86400, time) AS compare, time
    FROM (
      SELECT count(*) AS PV,
             histogram(__TIMESTAMP__, interval 5 minute) AS time
      GROUP BY time
    )
  )
```

### 基础对比示例

```sql
-- 日环比：对比昨天同时段的日志总量
* | SELECT compare(count(*), 86400) as result

-- 同时对比昨天和上周
* | SELECT compare(count(*), 86400, 604800) as result
```

### 注意事项
- 查询的时间范围必须能覆盖到当前值和历史值（如日环比需要至少能访问到 24 小时前的数据）
- 趋势对比的 `time_column` 参数必须是 `timestamp` 类型
- 趋势对比的子查询中必须包含 `GROUP BY time`

---

## 8. IP 地理函数

CLS 提供内置的 IP 地理位置解析函数，无需额外配置。

### 函数列表

| 函数 | 说明 | 返回值 |
|------|------|--------|
| `ip_to_country(ip)` | IP → 国家 | 国家名称 |
| `ip_to_province(ip)` | IP → 省份 | 省份名称 |
| `ip_to_city(ip)` | IP → 城市 | 城市名称 |
| `ip_to_provider(ip)` | IP → 运营商 | 运营商名称（电信/联通/移动等） |
| `ip_to_domain(ip)` | IP → 内外网判断 | `'inland'`（国内）/ `'outland'`（国外） |

### 网段计算函数

| 函数 | 说明 | 返回值 |
|------|------|--------|
| `ip_prefix(ip, prefix_bits)` | 计算子网前缀 | 子网地址，如 `'192.168.1.0'` |
| `ip_subnet_min(ip, prefix_bits)` | 子网最小 IP | 最小 IP 地址 |
| `ip_subnet_max(ip, prefix_bits)` | 子网最大 IP | 最大 IP 地址 |
| `is_subnet_of(ip, cidr)` | 判断 IP 是否在子网内 | `true` / `false` |

### 示例

```sql
-- 按省份统计访问量 Top10
* | SELECT ip_to_province(client_ip) as province,
         COUNT(*) as cnt
  GROUP BY province
  ORDER BY cnt DESC
  LIMIT 10

-- 判断内外网访问分布
* | SELECT ip_to_domain(client_ip) as domain, COUNT(*) as cnt
  GROUP BY domain

-- 查找特定子网的访问
* | SELECT client_ip, COUNT(*) as cnt
  WHERE is_subnet_of(client_ip, '192.168.0.0/16')
  GROUP BY client_ip
  ORDER BY cnt DESC
```

### 注意
- 内网 IP（如 10.x.x.x、172.16-31.x.x、192.168.x.x）地理函数返回空或 NULL
- 建议配合 `WHERE client_ip != ''` 过滤空 IP

---

## 9. IP 威胁情报函数

CLS 内置 IP 威胁情报查询能力。

### 函数列表

| 函数 | 说明 | 返回值 |
|------|------|--------|
| `ip_to_threat_type(ip)` | IP 威胁类型 | 威胁类型描述 |
| `ip_to_threat_level(ip)` | IP 威胁等级 | 0-4 等级（0=正常，4=最高危） |

### 示例

```sql
-- 查找高危访问 IP
* | SELECT client_ip,
         ip_to_threat_type(client_ip) as threat_type,
         ip_to_threat_level(client_ip) as threat_level,
         COUNT(*) as cnt
  GROUP BY client_ip, threat_type, threat_level
  HAVING threat_level > 0
  ORDER BY threat_level DESC, cnt DESC
  LIMIT 20
```

---

## 10. 类型转换

### cast 与 try_cast

| 函数 | 说明 |
|------|------|
| `cast(value AS type)` | 类型转换，失败则**终止整个查询** |
| `try_cast(value AS type)` | 类型转换，失败则返回 **NULL**（继续执行） |

⚠️ 日志数据经常有脏数据，**建议优先使用 `try_cast`** 避免查询中断。

### 常用转换模式

```sql
-- __TIMESTAMP__ 转 timestamp（UTC+0）
cast(__TIMESTAMP__ as timestamp)

-- 字符串转数值（安全模式）
try_cast(response_time as double)

-- 字符串转时间戳
cast('2024-01-01T00:00:00.000Z' as timestamp)

-- 用 date_parse 转换自定义格式字符串
date_parse(time_str, '%Y-%m-%d %H:%i:%s')
```

### __TIMESTAMP__ 的类型说明
- `__TIMESTAMP__` 是 **bigint** 类型，值为**毫秒级** Unix 时间戳
- `cast(__TIMESTAMP__ as timestamp)` 转换结果为 **UTC+0** 时区
- `from_unixtime` 接受**秒级**时间戳，因此必须除以 1000：`from_unixtime(__TIMESTAMP__/1000)`

---

## 11. 日期时间函数（高频使用）

### from_unixtime

```sql
-- 秒级时间戳转 timestamp（UTC+0）
from_unixtime(__TIMESTAMP__/1000)

-- 指定时区转换为北京时间（推荐）
from_unixtime(__TIMESTAMP__/1000, 'Asia/Shanghai')
```

⚠️ `__TIMESTAMP__` 是毫秒级，`from_unixtime` 接受秒级，**必须除以 1000**。

### date_trunc — 时间截断

```sql
-- 截断到小时（UTC+0，非北京时间！）
date_trunc('hour', cast(__TIMESTAMP__ as timestamp))

-- 截断到北京时间的小时
date_trunc('hour', cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR)
```

支持粒度：`second`、`minute`、`hour`、`day`、`week`（周一）、`month`、`quarter`、`year`

### date_format — 时间格式化

```sql
-- 格式化为字符串（UTC+0）
date_format(cast(__TIMESTAMP__ as timestamp), '%Y-%m-%d %H:%i:%s')

-- 格式化为北京时间字符串
date_format(cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR, '%Y-%m-%d %H:%i:%s')

-- 或用 from_unixtime 指定时区
date_format(from_unixtime(__TIMESTAMP__/1000, 'Asia/Shanghai'), '%Y-%m-%d %H:%i:%s')
```

### 格式符速查

| 格式符 | 含义 | 示例 |
|--------|------|------|
| `%Y` | 4 位年份 | 2024 |
| `%m` | 月（01-12） | 03 |
| `%d` | 日（01-31） | 25 |
| `%H` | 小时（24h） | 14 |
| **`%i`** | **分钟（00-59）** | 30 |
| `%s` | 秒（00-59） | 45 |
| `%f` | 毫秒/微秒 | 123000 |

⚠️ **`%i` 是分钟，`%M` 是英文月份名**（如 January），这是最常见的格式符错误。

### date_parse — 字符串转时间

```sql
-- 自定义格式字符串转 timestamp
date_parse('2024-03-25 14:30:00', '%Y-%m-%d %H:%i:%s')
```

### date_add / date_diff

```sql
-- 加减时间
date_add('hour', 8, cast(__TIMESTAMP__ as timestamp))   -- 加 8 小时
date_add('day', -7, cast(__TIMESTAMP__ as timestamp))    -- 减 7 天

-- 计算时间差
date_diff('hour', timestamp1, timestamp2)
```

### extract — 提取时间部分

```sql
-- 提取小时
extract(hour from cast(__TIMESTAMP__ as timestamp))
-- 简化写法
hour(cast(__TIMESTAMP__ as timestamp))
```

支持字段：`year`、`quarter`、`month`、`week`、`day`、`day_of_week`（dow）、`day_of_year`（doy）、`hour`、`minute`、`second`

---

## 12. 条件表达式

```sql
-- CASE WHEN
* | SELECT CASE
      WHEN status >= 500 THEN '5xx'
      WHEN status >= 400 THEN '4xx'
      WHEN status >= 300 THEN '3xx'
      ELSE '2xx'
    END as status_group,
    COUNT(*) as cnt
  GROUP BY status_group

-- IF 函数
* | SELECT IF(status >= 400, 'error', 'ok') as type, COUNT(*) as cnt
  GROUP BY type

-- COALESCE（返回第一个非 NULL 值）
* | SELECT COALESCE(user_id, 'anonymous') as uid
```

---

## 13. JSON 函数

```sql
-- 提取 JSON 字段值（返回 JSON 类型）
json_extract(json_field, '$.user.name')

-- 提取 JSON 字段值（返回 varchar 类型，更常用）
json_extract_scalar(json_field, '$.user.name')

-- 示例：提取嵌套 JSON 中的字段做统计
* | SELECT json_extract_scalar(body, '$.action') as action,
         COUNT(*) as cnt
  GROUP BY action
  ORDER BY cnt DESC
```

---

## 14. 估算函数

```sql
-- 近似去重计数（比 COUNT(DISTINCT) 更快，适合大数据量）
* | SELECT APPROX_DISTINCT(user_id) as uv

-- 近似百分位
* | SELECT APPROX_PERCENTILE(response_time, 0.50) as p50,
         APPROX_PERCENTILE(response_time, 0.95) as p95,
         APPROX_PERCENTILE(response_time, 0.99) as p99
```

---

## 15. URL 函数

```sql
-- 提取 URL 各部分
* | SELECT url_extract_host(request_url) as host,
         url_extract_path(request_url) as path,
         url_extract_parameter(request_url, 'id') as param_id,
         COUNT(*) as cnt
  GROUP BY host, path, param_id
```

---

## 16. 正则函数

```sql
-- 正则匹配判断
* | SELECT * WHERE regexp_like(url, '/api/v[0-9]+/users')

-- 正则提取
* | SELECT regexp_extract(url, '/api/(v[0-9]+)/', 1) as api_version,
         COUNT(*) as cnt
  GROUP BY api_version

-- 正则替换
* | SELECT regexp_replace(phone, '(\d{3})\d{4}(\d{4})', '$1****$2') as masked_phone
```

---

## 17. 内置字段

CLS 提供以下内置字段，在 SQL 分析中可直接使用：

| 字段 | 类型 | 说明 |
|------|------|------|
| `__TIMESTAMP__` | bigint | 日志采集时间，**毫秒级** Unix 时间戳 |
| `__SOURCE__` | varchar | 日志来源（通常为采集机器 IP） |
| `__FILENAME__` | varchar | 日志文件名 |

---

## 18. 通用注意事项

1. **FROM 子句**：CLS SQL 不需要写 `FROM`，默认从管道符左侧的检索结果中分析
2. **默认返回行数**：默认 100 行，最大 100 万行
3. **查询大小限制**：查询语句最大 10KB
4. **字段引用**：字段名包含特殊字符或与保留字冲突时用双引号包裹，如 `"select"`
5. **字符串必须用单引号**：`'hello'`，不是 `"hello"`
6. **不需要分号结尾**：SQL 语句末尾不加 `;`
7. **嵌套 JSON**：用 `json_extract_scalar()` 提取嵌套字段
8. **APPROX 函数**：`APPROX_DISTINCT()`、`APPROX_PERCENTILE()` 等与 Trino 一致
9. **低频存储**：低频存储不支持 SQL 分析，仅支持检索
10. **时区陷阱**：除 histogram 和 time_series（传 LONG 型）外，所有日期时间函数默认 UTC+0，需手动加 8 小时得到北京时间
