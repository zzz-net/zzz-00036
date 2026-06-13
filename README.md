# 试剂留样交接 JSON API

基于 FastAPI + SQLite 的试剂留样管理系统，支持批次登记、领取、归还、复核封存、报废全流程，并提供完整的审计日志和导出功能。

## 技术栈

- **后端框架**: FastAPI
- **数据库**: SQLite（文件持久化，重启不丢数据）
- **ORM**: SQLAlchemy
- **数据校验**: Pydantic

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

服务启动后访问:
- API 文档 (Swagger UI): http://127.0.0.1:8000/docs
- 健康检查: http://127.0.0.1:8000/api/health

### 3. 初始化数据

服务首次启动时会自动初始化样例数据：

**用户**:
- `alice` - 普通操作员 (operator)
- `bob` - 普通操作员 (operator)
- `charlie` - 复核员 (reviewer)

**库位**:
- `A-01` - 冷藏柜A-01 (容量 50)
- `A-02` - 冷藏柜A-02 (容量 30)
- `B-01` - 常温柜B-01 (容量 100)

**批次**:
- `REAG-2026-0001` - PCR反应试剂盒 (20份, 冷藏柜A-01, 有效期至 2027-06-01)
- `REAG-2026-0002` - 抗原检测试剂 (50份, 常温柜B-01, 有效期至 2026-12-31)

---

## 核心概念

### 角色

| 角色 | 权限 |
|------|------|
| `operator` (操作员) | 登记批次、领取留样、归还留样、查看调拨记录、提交温控巡检记录、查看自己提交的巡检记录 |
| `reviewer` (复核员) | 所有操作员权限 + 复核封存、报废、冻结/解冻库位、发起批次调拨、配置温控监控、处理温控异常单 |

### 状态流转

```
REGISTERED (已登记/在库)
    |
    v  领取
IN_USE (领用中)
    |
    v  归还
PENDING_REVIEW (待复核)
    |          \
    v 封存      v 报废
SEALED       SCRAPPED
(已封存)      (已报废)
```

---

## API 接口总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/users` | 用户列表 |
| POST | `/api/users` | 创建用户 |
| GET | `/api/locations` | 库位列表 |
| POST | `/api/locations` | 创建库位 |
| GET | `/api/batches` | 批次列表 |
| POST | `/api/batches` | 登记批次 |
| GET | `/api/batches/{batch_no}` | 批次详情 |
| POST | `/api/batches/{batch_no}/pickup` | 领取留样 |
| POST | `/api/batches/{batch_no}/return` | 归还留样 |
| POST | `/api/batches/{batch_no}/seal` | 复核封存 |
| POST | `/api/batches/{batch_no}/scrap` | 报废 |
| GET | `/api/audit-logs` | 审计日志查询 |
| GET | `/api/export/audit` | 导出审计日志 |

---

## 完整 curl 链路示例

> 所有示例默认服务运行在 `127.0.0.1:8000`

### 一、成功路径：建档 → 领取 → 归还 → 封存 → 查询 → 导出

#### 1. 查看初始数据

```bash
# 查看用户列表
curl -s http://127.0.0.1:8000/api/users | python -m json.tool

# 查看库位列表
curl -s http://127.0.0.1:8000/api/locations | python -m json.tool

# 查看批次列表
curl -s http://127.0.0.1:8000/api/batches | python -m json.tool
```

#### 2. 登记新批次（建档）

```bash
curl -s -X POST http://127.0.0.1:8000/api/batches \
  -H "Content-Type: application/json" \
  -d '{
    "batch_no": "REAG-2026-0003",
    "reagent_name": "酶联免疫试剂盒",
    "total_quantity": 30,
    "expiry_date": "2027-03-15",
    "location_code": "A-01",
    "username": "bob",
    "remark": "新批次入库，来自供应商XYZ"
  }' | python -m json.tool
```

字段说明：
- `username`: 登记人（必填，必须是已存在的用户）
- `remark`: 建档备注（可选）

预期结果：状态为 `REGISTERED`，可用数量 30。同时会写入一条 `REGISTER` 审计日志，记录登记人、角色和建档备注。

#### 3. 操作员领取留样

```bash
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0003/pickup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "quantity": 5,
    "remark": "质量检测用"
  }' | python -m json.tool
```

预期结果：状态变为 `IN_USE`，可用数量变为 25。

#### 4. 操作员归还留样

```bash
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0003/return \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "quantity": 3,
    "remark": "剩余3份归还，2份已使用"
  }' | python -m json.tool
```

预期结果：状态变为 `PENDING_REVIEW`，可用数量变为 28。

#### 5. 复核员封存

```bash
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0003/seal \
  -H "Content-Type: application/json" \
  -d '{
    "username": "charlie",
    "remark": "复核无误，予以封存"
  }' | python -m json.tool
```

预期结果：状态变为 `SEALED`。

#### 6. 查询审计日志

```bash
# 按批次查询
curl -s "http://127.0.0.1:8000/api/audit-logs?batch_no=REAG-2026-0003" | python -m json.tool

# 按人员查询
curl -s "http://127.0.0.1:8000/api/audit-logs?username=alice" | python -m json.tool
```

#### 7. 导出审计日志

```bash
# 按批次导出
curl -s "http://127.0.0.1:8000/api/export/audit?batch_no=REAG-2026-0003" \
  -o audit_export_batch.json

# 按人员导出
curl -s "http://127.0.0.1:8000/api/export/audit?username=alice" \
  -o audit_export_user.json

# 查看导出内容
python -m json.tool audit_export_batch.json
```

---

### 二、失败路径验证

#### 1. 普通操作员尝试封存（权限不足）

```bash
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0003/seal \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "remark": "尝试封存"
  }' | python -m json.tool
```

预期结果：HTTP 403，提示权限不足。**批次状态保持不变**。

验证：
```bash
curl -s http://127.0.0.1:8000/api/batches/REAG-2026-0003 | python -m json.tool
```

#### 2. 超数量领取

```bash
# 先确认可用数量
curl -s http://127.0.0.1:8000/api/batches/REAG-2026-0001 | python -m json.tool

# 尝试领取超过可用数量
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0001/pickup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "quantity": 100
  }' | python -m json.tool
```

预期结果：HTTP 400，提示领取数量超过可用库存。**可用数量不变**。

#### 3. 超数量归还

```bash
# 先领取 3 份
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0002/pickup \
  -H "Content-Type: application/json" \
  -d '{"username": "bob", "quantity": 3}' | python -m json.tool

# 尝试归还 10 份（超过已领用数量）
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0002/return \
  -H "Content-Type: application/json" \
  -d '{
    "username": "bob",
    "quantity": 10
  }' | python -m json.tool
```

预期结果：HTTP 400，提示归还数量超过已领用量。**可用数量不变**。

#### 4. 库位容量被占满

```bash
# 创建一个容量只有 2 的库位
curl -s -X POST http://127.0.0.1:8000/api/locations \
  -H "Content-Type: application/json" \
  -d '{
    "code": "C-01",
    "name": "迷你柜C-01",
    "capacity": 2
  }' | python -m json.tool

# 放入第 1 个批次
curl -s -X POST http://127.0.0.1:8000/api/batches \
  -H "Content-Type: application/json" \
  -d '{
    "batch_no": "TEST-CAP-001",
    "reagent_name": "测试试剂1",
    "total_quantity": 10,
    "expiry_date": "2027-01-01",
    "location_code": "C-01",
    "username": "alice"
  }' | python -m json.tool

# 放入第 2 个批次
curl -s -X POST http://127.0.0.1:8000/api/batches \
  -H "Content-Type: application/json" \
  -d '{
    "batch_no": "TEST-CAP-002",
    "reagent_name": "测试试剂2",
    "total_quantity": 10,
    "expiry_date": "2027-01-01",
    "location_code": "C-01",
    "username": "alice"
  }' | python -m json.tool

# 放入第 3 个批次（应该失败，容量已满）
curl -s -X POST http://127.0.0.1:8000/api/batches \
  -H "Content-Type: application/json" \
  -d '{
    "batch_no": "TEST-CAP-003",
    "reagent_name": "测试试剂3",
    "total_quantity": 10,
    "expiry_date": "2027-01-01",
    "location_code": "C-01",
    "username": "alice"
  }' | python -m json.tool
```

预期结果：HTTP 400，提示库位容量已满。**库位已用数量不变**。

验证库位状态：
```bash
curl -s http://127.0.0.1:8000/api/locations/C-01 | python -m json.tool
```

#### 5. 状态错误的操作

```bash
# 已封存的批次不能再领取
curl -s -X POST http://127.0.0.1:8000/api/batches/REAG-2026-0003/pickup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "quantity": 1
  }' | python -m json.tool
```

预期结果：HTTP 400，提示当前状态不能领取。

---

### 三、数据持久化验证

重启服务后数据保持一致：

```bash
# 1. 停止服务 (Ctrl+C)

# 2. 重新启动
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# 3. 验证批次状态
curl -s http://127.0.0.1:8000/api/batches/REAG-2026-0003 | python -m json.tool

# 4. 验证库存数量
curl -s http://127.0.0.1:8000/api/batches | python -m json.tool

# 5. 验证审计历史
curl -s "http://127.0.0.1:8000/api/audit-logs?username=alice" | python -m json.tool

# 6. 验证导出内容和重启前一致
curl -s "http://127.0.0.1:8000/api/export/audit?batch_no=REAG-2026-0003" \
  -o audit_export_after_restart.json

diff audit_export_batch.json audit_export_after_restart.json
# 注意：export_time 字段会不同，其余记录内容一致
```

---

## 数据库文件

SQLite 数据库文件为 `reagent_sample.db`，位于项目根目录。删除此文件可重置所有数据（下次启动时会重新初始化）。

## 数据模型

### 用户 (User)
- `id`: 主键
- `username`: 用户名（唯一）
- `role`: 角色 (operator / reviewer)

### 库位 (Location)
- `id`: 主键
- `code`: 库位编码（唯一）
- `name`: 库位名称
- `capacity`: 总容量（可放批次数）
- `used`: 已用数量

### 批次 (Batch)
- `id`: 主键
- `batch_no`: 批次号（唯一）
- `reagent_name`: 试剂名称
- `total_quantity`: 总数量
- `available_quantity`: 可用数量
- `expiry_date`: 有效期
- `location_id`: 所属库位
- `status`: 状态

### 审计日志 (AuditLog)
- `id`: 主键
- `batch_id`: 批次ID
- `user_id`: 操作人ID
- `action`: 操作类型
- `quantity`: 操作数量
- `from_status`: 变更前状态
- `to_status`: 变更后状态
- `remark`: 备注
- `created_at`: 操作时间

### 库位操作日志 (LocationLog)
- `id`: 主键
- `location_id`: 库位ID
- `user_id`: 操作人ID
- `action`: 操作类型（FREEZE / UNFREEZE / TRANSFER_OUT / TRANSFER_IN）
- `remark`: 备注
- `created_at`: 操作时间

### 批次调拨记录 (BatchTransfer)
- `id`: 主键
- `batch_id`: 批次ID
- `from_location_id`: 源库位ID
- `to_location_id`: 目标库位ID
- `user_id`: 操作人ID（必须是 reviewer）
- `remark`: 调拨备注
- `created_at`: 调拨时间

### 温控巡检记录 (TemperatureInspection)
- `id`: 主键
- `location_id`: 库位ID
- `user_id`: 巡检人ID（operator 或 reviewer）
- `temperature`: 巡检温度（°C）
- `inspection_date`: 巡检日期（YYYY-MM-DD）
- `remark`: 备注
- `created_at`: 提交时间

### 温控异常单 (TemperatureAlert)
- `id`: 主键
- `location_id`: 库位ID
- `inspection_id`: 关联巡检记录ID
- `temperature`: 异常温度
- `temp_min`: 库位最低温度（快照）
- `temp_max`: 库位最高温度（快照）
- `status`: 状态（OPEN / HANDLED）
- `handler_id`: 处理人ID（必须是 reviewer）
- `reason`: 原因
- `disposal`: 处置说明
- `handled_at`: 处理时间
- `created_at`: 创建时间

---

## 温控巡检模块

### 完整流程示例

#### 1. 复核员为库位启用温控监控

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temp-config \
  -H "Content-Type: application/json" \
  -d '{
    "username": "charlie",
    "monitoring_enabled": true,
    "temp_min": 2.0,
    "temp_max": 8.0
  }' | python -m json.tool
```

预期结果：`monitoring_enabled` 为 true，`temp_min` 为 2.0，`temp_max` 为 8.0。

#### 2. 操作员提交正常巡检记录

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temperature-inspections \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "temperature": 4.5,
    "inspection_date": "2026-06-13",
    "remark": "上午巡检，温度正常"
  }' | python -m json.tool
```

预期结果：返回巡检记录，温度 4.5°C 在 2~8°C 范围内，不产生异常单。

#### 3. 操作员提交超温巡检记录（自动生成异常单）

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temperature-inspections \
  -H "Content-Type: application/json" \
  -d '{
    "username": "bob",
    "temperature": 10.5,
    "inspection_date": "2026-06-13",
    "remark": "温度偏高"
  }' | python -m json.tool
```

预期结果：返回巡检记录，同时系统自动生成一条 OPEN 状态的异常单。

#### 4. 查询异常单

```bash
curl -s "http://127.0.0.1:8000/api/temperature-alerts?status=OPEN" | python -m json.tool
```

#### 5. 复核员处理异常单

```bash
curl -s -X POST http://127.0.0.1:8000/api/temperature-alerts/1/handle \
  -H "Content-Type: application/json" \
  -d '{
    "username": "charlie",
    "reason": "冷柜门未关紧导致温度升高",
    "disposal": "已关紧柜门，温度已恢复正常，持续观察"
  }' | python -m json.tool
```

预期结果：异常单状态变为 HANDLED，记录处理人、原因和处置说明。

#### 6. 查询巡检记录

```bash
# 按库位查询
curl -s "http://127.0.0.1:8000/api/locations/A-01/temperature-inspections" | python -m json.tool

# 按日期查询
curl -s "http://127.0.0.1:8000/api/temperature-inspections?inspection_date=2026-06-13" | python -m json.tool

# 按提交人查询
curl -s "http://127.0.0.1:8000/api/temperature-inspections?username=alice" | python -m json.tool
```

#### 7. 导出巡检和异常记录

```bash
curl -s "http://127.0.0.1:8000/api/export/temperature?location_code=A-01" \
  -o temperature_export.json

python -m json.tool temperature_export.json
```

---

### 温控巡检失败路径验证

#### 1. operator 尝试配置温控监控（权限不足）

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temp-config \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "monitoring_enabled": true,
    "temp_min": 2.0,
    "temp_max": 8.0
  }' | python -m json.tool
```

预期结果：HTTP 403。

#### 2. 未启用监控的库位提交巡检

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/B-01/temperature-inspections \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "temperature": 25.0,
    "inspection_date": "2026-06-13"
  }' | python -m json.tool
```

预期结果：HTTP 400，提示库位未启用温控监控。

#### 3. 温度格式非法

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temperature-inspections \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "temperature": "abc",
    "inspection_date": "2026-06-13"
  }' | python -m json.tool
```

预期结果：HTTP 422，校验失败。

#### 4. 同一用户同日对同一库位重复巡检

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temperature-inspections \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "temperature": 5.0,
    "inspection_date": "2026-06-13"
  }' | python -m json.tool
```

预期结果：HTTP 409，冲突。

#### 5. operator 尝试处理异常单（权限不足）

```bash
curl -s -X POST http://127.0.0.1:8000/api/temperature-alerts/1/handle \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "reason": "测试",
    "disposal": "测试"
  }' | python -m json.tool
```

预期结果：HTTP 403。

#### 6. 启用监控但未设置温度范围

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temp-config \
  -H "Content-Type: application/json" \
  -d '{
    "username": "charlie",
    "monitoring_enabled": true
  }' | python -m json.tool
```

预期结果：HTTP 400，提示必须设置温度范围。

#### 7. 最低温度 >= 最高温度

```bash
curl -s -X POST http://127.0.0.1:8000/api/locations/A-01/temp-config \
  -H "Content-Type: application/json" \
  -d '{
    "username": "charlie",
    "monitoring_enabled": true,
    "temp_min": 8.0,
    "temp_max": 2.0
  }' | python -m json.tool
```

预期结果：HTTP 400，提示最低温度必须小于最高温度。
