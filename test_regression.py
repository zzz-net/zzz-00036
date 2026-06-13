import json
import sys
import time
import requests
import os

BASE = "http://127.0.0.1:8000"

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} - {detail}")


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


BATCH_ID = None


def run_phase1():
    global passed, failed, BATCH_ID
    passed = 0
    failed = 0

    section("1. 建档（登记批次）- 带登记人和备注")
    resp = requests.post(f"{BASE}/api/batches", json={
        "batch_no": "REG-TEST-001",
        "reagent_name": "回归测试试剂A",
        "total_quantity": 20,
        "expiry_date": "2027-06-30",
        "location_code": "A-01",
        "username": "bob",
        "remark": "建档备注：2026年6月采购入库"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200)
    check("batch_no 正确", d.get("batch_no") == "REG-TEST-001")
    check("状态 REGISTERED", d.get("status") == "REGISTERED")
    check("可用数量 = 20", d.get("available_quantity") == 20)
    BATCH_ID = d.get("id")

    section("2. 建档审计 - 检查 REGISTER 日志是否写入")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"batch_no": "REG-TEST-001"})
    d = resp.json()
    logs = d["items"]
    print(f"  审计日志条数: {d['total']}")
    check("至少有 1 条审计记录", d["total"] >= 1)
    reg_log = None
    for log in logs:
        if log["action"] == "REGISTER":
            reg_log = log
            break
    check("存在 REGISTER 动作", reg_log is not None, "未找到 REGISTER 审计记录")
    if reg_log:
        check("登记人是 bob", reg_log.get("username") == "bob", f"实际: {reg_log.get('username')}")
        check("登记人角色是 operator", reg_log.get("user_role") == "operator", f"实际: {reg_log.get('user_role')}")
        check("建档备注正确", "采购入库" in (reg_log.get("remark") or ""), f"实际: {reg_log.get('remark')}")
        check("记录数量 20", reg_log.get("quantity") == 20, f"实际: {reg_log.get('quantity')}")
        check("from_status 为 None/空", reg_log.get("from_status") is None or reg_log.get("from_status") == "", f"实际: {reg_log.get('from_status')}")
        check("to_status 为 REGISTERED", reg_log.get("to_status") == "REGISTERED", f"实际: {reg_log.get('to_status')}")

    section("3. 领取留样")
    resp = requests.post(f"{BASE}/api/batches/REG-TEST-001/pickup", json={
        "username": "alice",
        "quantity": 5,
        "remark": "领取用于项目X"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200)
    check("状态变为 IN_USE", d.get("status") == "IN_USE", f"实际: {d.get('status')}")
    check("可用数量 = 15", d.get("available_quantity") == 15, f"实际: {d.get('available_quantity')}")

    section("4. 归还留样")
    resp = requests.post(f"{BASE}/api/batches/REG-TEST-001/return", json={
        "username": "alice",
        "quantity": 3,
        "remark": "使用2份，归还3份"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200)
    check("状态变为 PENDING_REVIEW", d.get("status") == "PENDING_REVIEW", f"实际: {d.get('status')}")
    check("可用数量 = 18", d.get("available_quantity") == 18, f"实际: {d.get('available_quantity')}")

    section("5. 复核封存")
    resp = requests.post(f"{BASE}/api/batches/REG-TEST-001/seal", json={
        "username": "charlie",
        "remark": "复核无误，予以封存"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200)
    check("状态变为 SEALED", d.get("status") == "SEALED", f"实际: {d.get('status')}")

    section("6. 按批次查询审计 - 检查完整状态历史")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"batch_no": "REG-TEST-001"})
    d = resp.json()
    logs = d["items"]
    print(f"  审计日志总条数: {d['total']}")
    actions = [log["action"] for log in logs]
    print(f"  动作序列(从新到旧): {actions}")
    check("共 4 条审计记录", d["total"] == 4, f"实际: {d['total']}")
    check("包含 REGISTER", "REGISTER" in actions)
    check("包含 PICKUP", "PICKUP" in actions)
    check("包含 RETURN", "RETURN" in actions)
    check("包含 SEAL", "SEAL" in actions)

    for log in logs:
        print(f"    - {log['action']}: {log['username']}({log['user_role']}), 数量={log['quantity']}, {log['from_status']} -> {log['to_status']}, 备注={log.get('remark')}")

    check("每条记录都有 username", all(log.get("username") for log in logs))
    check("每条记录都有 user_role", all(log.get("user_role") for log in logs))

    section("7. 按人员查询审计 (bob - 登记人)")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"username": "bob"})
    d = resp.json()
    print(f"  bob 的审计记录数: {d['total']}")
    check("bob 至少 1 条记录", d["total"] >= 1)
    bob_actions = [log["action"] for log in d["items"]]
    print(f"  bob 的动作: {bob_actions}")
    check("bob 有 REGISTER 记录", "REGISTER" in bob_actions)

    section("8. 按人员查询审计 (alice - 操作员)")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"username": "alice"})
    d = resp.json()
    print(f"  alice 的审计记录数: {d['total']}")
    check("alice 至少 2 条记录", d["total"] >= 2)
    alice_actions = [log["action"] for log in d["items"]]
    print(f"  alice 的动作: {alice_actions}")
    check("alice 有 PICKUP 记录", "PICKUP" in alice_actions)
    check("alice 有 RETURN 记录", "RETURN" in alice_actions)

    section("9. 按人员查询审计 (charlie - 复核员)")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"username": "charlie"})
    d = resp.json()
    print(f"  charlie 的审计记录数: {d['total']}")
    check("charlie 至少 1 条记录", d["total"] >= 1)
    charlie_actions = [log["action"] for log in d["items"]]
    print(f"  charlie 的动作: {charlie_actions}")
    check("charlie 有 SEAL 记录", "SEAL" in charlie_actions)

    section("10. 导出审计 - 按批次")
    resp = requests.get(f"{BASE}/api/export/audit", params={"batch_no": "REG-TEST-001"})
    export_data = resp.json()
    print(f"  导出记录数: {export_data['total']}")
    check("导出 total=4", export_data["total"] == 4, f"实际: {export_data['total']}")
    check("导出有 records 字段", "records" in export_data)
    check("导出 records 长度=4", len(export_data["records"]) == 4, f"实际: {len(export_data['records'])}")

    export_actions = [r["action"] for r in export_data["records"]]
    print(f"  导出动作: {export_actions}")
    check("导出包含 REGISTER", "REGISTER" in export_actions)
    check("导出每条都有 operator", all(r.get("operator") for r in export_data["records"]))
    check("导出每条都有 operator_role", all(r.get("operator_role") for r in export_data["records"]))

    with open("export_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print("  已保存 export_before_restart.json")

    section("11. 导出审计 - 按人员 (bob)")
    resp = requests.get(f"{BASE}/api/export/audit", params={"username": "bob"})
    export_data = resp.json()
    print(f"  bob 的导出记录数: {export_data['total']}")
    check("bob 导出至少 1 条", export_data["total"] >= 1)
    for r in export_data["records"]:
        print(f"    operator={r['operator']}, role={r['operator_role']}, action={r['action']}")
        check("导出 operator=bob", r["operator"] == "bob")
        check("导出 operator_role=operator", r["operator_role"] == "operator")

    section("12. 失败路径：普通操作员尝试封存")
    resp = requests.post(f"{BASE}/api/batches/REAG-2026-0002/seal", json={
        "username": "alice"
    })
    print(f"  HTTP {resp.status_code}")
    check("状态码 403", resp.status_code == 403, f"实际: {resp.status_code}")
    check("返回错误信息含 '权限'", "权限" in resp.json().get("detail", ""))

    resp2 = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    d = resp2.json()
    print(f"  批次 REAG-2026-0002 当前状态: {d.get('status')}")
    check("状态保持 REGISTERED 不变", d.get("status") == "REGISTERED", f"实际: {d.get('status')}")

    section("13. 失败路径：超数量领取")
    resp = requests.post(f"{BASE}/api/batches/REAG-2026-0002/pickup", json={
        "username": "alice",
        "quantity": 999
    })
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("返回错误信息含 '超过'", "超过" in resp.json().get("detail", ""))

    resp2 = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    d = resp2.json()
    print(f"  批次 REAG-2026-0002 可用数量: {d.get('available_quantity')}")
    check("可用数量保持 50 不变", d.get("available_quantity") == 50, f"实际: {d.get('available_quantity')}")

    section("14. 库位管理 - 冻结/解冻")

    section("14.1 库位列表包含 frozen 字段")
    resp = requests.get(f"{BASE}/api/locations")
    d = resp.json()
    print(f"  库位数量: {d['total']}")
    check("状态码 200", resp.status_code == 200)
    check("每个库位都有 frozen 字段", all("frozen" in loc for loc in d["items"]))
    loc_a02 = [loc for loc in d["items"] if loc["code"] == "A-02"][0]
    check("A-02 初始未冻结", loc_a02["frozen"] == False, f"实际: {loc_a02['frozen']}")
    loc_a02_used_before = loc_a02["used"]

    section("14.2 复核员冻结 A-02 库位")
    resp = requests.post(f"{BASE}/api/locations/A-02/freeze", json={
        "username": "charlie",
        "remark": "设备检修，临时冻结"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("frozen 变为 True", d.get("frozen") == True, f"实际: {d.get('frozen')}")

    section("14.3 冻结后登记新批次到 A-02 应失败")
    resp = requests.post(f"{BASE}/api/batches", json={
        "batch_no": "FREEZE-TEST-001",
        "reagent_name": "冻结测试试剂",
        "total_quantity": 10,
        "expiry_date": "2027-01-01",
        "location_code": "A-02",
        "username": "alice"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '冻结'", "冻结" in d.get("detail", ""), f"实际: {d.get('detail')}")

    resp2 = requests.get(f"{BASE}/api/locations/A-02")
    d2 = resp2.json()
    print(f"  A-02 已用数量: {d2.get('used')}")
    check("库位已用数量不变", d2.get("used") == loc_a02_used_before, f"实际: {d2.get('used')}")

    section("14.4 普通操作员尝试冻结（权限不足）")
    resp = requests.post(f"{BASE}/api/locations/A-01/freeze", json={
        "username": "alice",
        "remark": "越权尝试冻结"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 403", resp.status_code == 403, f"实际: {resp.status_code}")
    check("错误信息含 '权限'", "权限" in d.get("detail", ""), f"实际: {d.get('detail')}")

    resp2 = requests.get(f"{BASE}/api/locations/A-01")
    d2 = resp2.json()
    print(f"  A-01 冻结状态: {d2.get('frozen')}")
    check("A-01 仍未冻结（状态未改变）", d2.get("frozen") == False, f"实际: {d2.get('frozen')}")

    section("14.5 查询库位操作日志 - 按库位")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-02"})
    d = resp.json()
    print(f"  A-02 日志条数: {d['total']}")
    check("至少有 1 条日志", d["total"] >= 1)
    logs = d["items"]
    check("最新日志为 FREEZE 动作", logs[0]["action"] == "FREEZE", f"实际: {logs[0]['action']}")
    check("操作人是 charlie", logs[0]["username"] == "charlie", f"实际: {logs[0]['username']}")
    check("操作人角色是 reviewer", logs[0]["user_role"] == "reviewer", f"实际: {logs[0]['user_role']}")
    check("备注含 '检修'", "检修" in (logs[0].get("remark") or ""), f"实际: {logs[0].get('remark')}")

    section("14.6 查询库位操作日志 - 按操作人")
    resp = requests.get(f"{BASE}/api/location-logs", params={"username": "charlie"})
    d = resp.json()
    print(f"  charlie 的库位日志条数: {d['total']}")
    check("charlie 至少有 1 条日志", d["total"] >= 1)
    charlie_actions = [log["action"] for log in d["items"]]
    check("charlie 有 FREEZE 记录", "FREEZE" in charlie_actions)

    section("14.7 导出库位操作日志")
    resp = requests.get(f"{BASE}/api/export/location-logs", params={"location_code": "A-02"})
    export_data = resp.json()
    print(f"  导出记录数: {export_data['total']}")
    check("导出 total >= 1", export_data["total"] >= 1)
    check("导出有 records 字段", "records" in export_data)
    check("导出 records 有 FREEZE", any(r["action"] == "FREEZE" for r in export_data["records"]))
    check("导出每条都有 operator", all(r.get("operator") for r in export_data["records"]))
    check("导出每条都有 operator_role", all(r.get("operator_role") for r in export_data["records"]))

    with open("location_log_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print("  已保存 location_log_before_restart.json")

    section("14.8 复核员解冻 A-02 库位")
    resp = requests.post(f"{BASE}/api/locations/A-02/unfreeze", json={
        "username": "charlie",
        "remark": "检修完成，解冻"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("frozen 变为 False", d.get("frozen") == False, f"实际: {d.get('frozen')}")

    section("14.9 解冻后登记新批次到 A-02 应成功")
    resp = requests.post(f"{BASE}/api/batches", json={
        "batch_no": "FREEZE-TEST-002",
        "reagent_name": "解冻后测试试剂",
        "total_quantity": 15,
        "expiry_date": "2027-03-01",
        "location_code": "A-02",
        "username": "bob",
        "remark": "解冻后登记的批次"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("批次号正确", d.get("batch_no") == "FREEZE-TEST-002")
    check("状态为 REGISTERED", d.get("status") == "REGISTERED")

    resp2 = requests.get(f"{BASE}/api/locations/A-02")
    d2 = resp2.json()
    print(f"  A-02 已用数量: {d2.get('used')}")
    check("库位已用数量 +1", d2.get("used") == loc_a02_used_before + 1, f"实际: {d2.get('used')}")

    section("14.10 再次冻结 A-02（保持状态用于重启验证）")
    resp = requests.post(f"{BASE}/api/locations/A-02/freeze", json={
        "username": "charlie",
        "remark": "重启验证用，保持冻结"
    })
    d = resp.json()
    check("再次冻结成功", resp.status_code == 200 and d.get("frozen") == True)

    section("14.11 已有冻结批次仍可正常查询和操作")
    resp = requests.get(f"{BASE}/api/batches/FREEZE-TEST-002")
    d = resp.json()
    print(f"  批次 FREEZE-TEST-002 状态: {d.get('status')}")
    check("批次可查询", resp.status_code == 200)
    check("批次状态为 REGISTERED", d.get("status") == "REGISTERED")

    resp = requests.post(f"{BASE}/api/batches/FREEZE-TEST-002/pickup", json={
        "username": "alice",
        "quantity": 3,
        "remark": "冻结库位上的批次仍可领取"
    })
    d = resp.json()
    print(f"  领取后状态: {d.get('status')}, 可用: {d.get('available_quantity')}")
    check("冻结库位上的批次可以领取", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("可用数量变为 12", d.get("available_quantity") == 12, f"实际: {d.get('available_quantity')}")

    section("14.12 保存重启前库位状态")
    resp = requests.get(f"{BASE}/api/locations/A-02")
    loc_before = resp.json()
    print(f"  A-02 重启前: frozen={loc_before['frozen']}, used={loc_before['used']}")
    with open("location_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(loc_before, f, ensure_ascii=False, indent=2)

    section("16. 批次调拨 - 成功路径")

    section("16.1 记录调拨前库位和批次状态")
    resp = requests.get(f"{BASE}/api/locations/B-01")
    b01_before = resp.json()
    print(f"  B-01 调拨前: used={b01_before['used']}")
    resp = requests.get(f"{BASE}/api/locations/A-01")
    a01_before = resp.json()
    print(f"  A-01 调拨前: used={a01_before['used']}")
    resp = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    batch_before = resp.json()
    print(f"  REAG-2026-0002 调拨前: location={batch_before['location_name']}")

    section("16.2 复核员成功调拨 REAG-2026-0002 从 B-01 到 A-01")
    resp = requests.post(f"{BASE}/api/batches/REAG-2026-0002/transfer", json={
        "username": "charlie",
        "to_location_code": "A-01",
        "remark": "常温转冷藏，试剂需低温保存"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("batch_no 正确", d.get("batch_no") == "REAG-2026-0002", f"实际: {d.get('batch_no')}")
    check("from_location_code = B-01", d.get("from_location_code") == "B-01", f"实际: {d.get('from_location_code')}")
    check("to_location_code = A-01", d.get("to_location_code") == "A-01", f"实际: {d.get('to_location_code')}")
    check("操作人是 charlie", d.get("username") == "charlie", f"实际: {d.get('username')}")
    check("操作人角色是 reviewer", d.get("user_role") == "reviewer", f"实际: {d.get('user_role')}")
    check("备注包含 '低温'", "低温" in (d.get("remark") or ""), f"实际: {d.get('remark')}")

    section("16.3 验证调拨后批次位置已更新")
    resp = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    batch_after = resp.json()
    print(f"  REAG-2026-0002 调拨后: location={batch_after['location_name']}")
    check("批次位置变为 A-01", batch_after["location_name"] == "冷藏柜A-01", f"实际: {batch_after['location_name']}")
    check("批次状态仍为 REGISTERED", batch_after["status"] == "REGISTERED", f"实际: {batch_after['status']}")

    section("16.4 验证调拨后源库位和目标库位 used 计数已更新")
    resp = requests.get(f"{BASE}/api/locations/B-01")
    b01_after = resp.json()
    print(f"  B-01 调拨后: used={b01_after['used']}")
    check("B-01 used -1", b01_after["used"] == b01_before["used"] - 1, f"实际: {b01_after['used']}, 预期: {b01_before['used'] - 1}")

    resp = requests.get(f"{BASE}/api/locations/A-01")
    a01_after = resp.json()
    print(f"  A-01 调拨后: used={a01_after['used']}")
    check("A-01 used +1", a01_after["used"] == a01_before["used"] + 1, f"实际: {a01_after['used']}, 预期: {a01_before['used'] + 1}")

    section("16.5 验证审计日志已写入 TRANSFER 记录")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"batch_no": "REAG-2026-0002"})
    d = resp.json()
    transfer_logs = [log for log in d["items"] if log["action"] == "TRANSFER"]
    print(f"  TRANSFER 审计日志条数: {len(transfer_logs)}")
    check("存在 TRANSFER 审计记录", len(transfer_logs) >= 1)
    if transfer_logs:
        log = transfer_logs[0]
        check("审计操作人是 charlie", log.get("username") == "charlie")
        check("审计操作人角色是 reviewer", log.get("user_role") == "reviewer")
        check("审计备注包含 A-01", "A-01" in (log.get("remark") or ""))
        check("审计备注包含 B-01", "B-01" in (log.get("remark") or ""))

    section("16.6 验证库位日志已写入 TRANSFER_OUT 和 TRANSFER_IN")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "B-01"})
    d = resp.json()
    b01_transfer_out = [log for log in d["items"] if log["action"] == "TRANSFER_OUT"]
    print(f"  B-01 TRANSFER_OUT 日志条数: {len(b01_transfer_out)}")
    check("B-01 存在 TRANSFER_OUT 日志", len(b01_transfer_out) >= 1)
    if b01_transfer_out:
        check("B-01 TRANSFER_OUT 操作人是 charlie", b01_transfer_out[0].get("username") == "charlie")

    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-01"})
    d = resp.json()
    a01_transfer_in = [log for log in d["items"] if log["action"] == "TRANSFER_IN"]
    print(f"  A-01 TRANSFER_IN 日志条数: {len(a01_transfer_in)}")
    check("A-01 存在 TRANSFER_IN 日志", len(a01_transfer_in) >= 1)
    if a01_transfer_in:
        check("A-01 TRANSFER_IN 操作人是 charlie", a01_transfer_in[0].get("username") == "charlie")

    section("17. 批次调拨 - 查询调拨记录")

    section("17.1 按批次查询调拨记录")
    resp = requests.get(f"{BASE}/api/transfers", params={"batch_no": "REAG-2026-0002"})
    d = resp.json()
    print(f"  按批次查询调拨记录数: {d['total']}")
    check("至少 1 条调拨记录", d["total"] >= 1)
    if d["items"]:
        t = d["items"][0]
        check("batch_no 正确", t["batch_no"] == "REAG-2026-0002")
        check("from_location_code = B-01", t["from_location_code"] == "B-01")
        check("to_location_code = A-01", t["to_location_code"] == "A-01")
        check("操作人是 charlie", t["username"] == "charlie")

    section("17.2 按源库位查询调拨记录")
    resp = requests.get(f"{BASE}/api/transfers", params={"from_location_code": "B-01"})
    d = resp.json()
    print(f"  按源库位 B-01 查询: {d['total']} 条")
    check("至少 1 条记录", d["total"] >= 1)
    check("所有记录 from_location_code = B-01", all(t["from_location_code"] == "B-01" for t in d["items"]))

    section("17.3 按目标库位查询调拨记录")
    resp = requests.get(f"{BASE}/api/transfers", params={"to_location_code": "A-01"})
    d = resp.json()
    print(f"  按目标库位 A-01 查询: {d['total']} 条")
    check("至少 1 条记录", d["total"] >= 1)
    check("所有记录 to_location_code = A-01", all(t["to_location_code"] == "A-01" for t in d["items"]))

    section("17.4 按操作人查询调拨记录")
    resp = requests.get(f"{BASE}/api/transfers", params={"username": "charlie"})
    d = resp.json()
    print(f"  按 charlie 查询: {d['total']} 条")
    check("至少 1 条记录", d["total"] >= 1)
    check("所有操作人是 charlie", all(t["username"] == "charlie" for t in d["items"]))

    section("17.5 operator 可以查询调拨记录（只读权限）")
    resp = requests.get(f"{BASE}/api/transfers")
    d = resp.json()
    check("operator 查询不报错", resp.status_code == 200)
    check("返回列表格式", "items" in d and "total" in d)

    section("18. 批次调拨 - 导出调拨记录")
    resp = requests.get(f"{BASE}/api/export/transfers", params={"batch_no": "REAG-2026-0002"})
    export_data = resp.json()
    print(f"  导出调拨记录数: {export_data['total']}")
    check("导出 total >= 1", export_data["total"] >= 1)
    check("导出有 records 字段", "records" in export_data)
    check("导出 records 有 batch_no=REAG-2026-0002",
          any(r["batch_no"] == "REAG-2026-0002" for r in export_data["records"]))
    check("导出每条都有 operator", all(r.get("operator") for r in export_data["records"]))
    check("导出每条都有 operator_role", all(r.get("operator_role") for r in export_data["records"]))
    check("导出每条都有 from_location_code", all(r.get("from_location_code") for r in export_data["records"]))
    check("导出每条都有 to_location_code", all(r.get("to_location_code") for r in export_data["records"]))

    with open("transfers_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print("  已保存 transfers_before_restart.json")

    section("19. 批次调拨 - 失败路径验证")

    section("19.1 普通操作员尝试调拨（权限不足）")
    resp = requests.post(f"{BASE}/api/batches/REAG-2026-0001/transfer", json={
        "username": "alice",
        "to_location_code": "A-02"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 403", resp.status_code == 403, f"实际: {resp.status_code}")
    check("错误信息含 '权限'", "权限" in d.get("detail", ""), f"实际: {d.get('detail')}")

    resp2 = requests.get(f"{BASE}/api/batches/REAG-2026-0001")
    batch_check = resp2.json()
    check("批次位置未变", batch_check["location_name"] == "冷藏柜A-01", f"实际: {batch_check['location_name']}")

    section("19.2 同库位调拨（源库位=目标库位）")
    resp = requests.post(f"{BASE}/api/batches/REAG-2026-0002/transfer", json={
        "username": "charlie",
        "to_location_code": "A-01"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '相同'", "相同" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("19.3 目标库位已冻结")
    resp = requests.post(f"{BASE}/api/batches/REAG-2026-0001/transfer", json={
        "username": "charlie",
        "to_location_code": "A-02"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '冻结'", "冻结" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("19.4 目标库位容量已满")
    requests.post(f"{BASE}/api/locations", json={
        "code": "TF-FULL-01",
        "name": "调拨满库位测试",
        "capacity": 1
    })
    requests.post(f"{BASE}/api/batches", json={
        "batch_no": "TF-FULL-BATCH-01",
        "reagent_name": "占库位试剂",
        "total_quantity": 5,
        "expiry_date": "2027-01-01",
        "location_code": "TF-FULL-01",
        "username": "bob"
    })
    resp = requests.post(f"{BASE}/api/batches/REAG-2026-0001/transfer", json={
        "username": "charlie",
        "to_location_code": "TF-FULL-01"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '已满'", "已满" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("19.5 已封存批次不能调拨")
    requests.post(f"{BASE}/api/locations", json={
        "code": "TF-SEALED-LOC",
        "name": "封存测试库位",
        "capacity": 10
    })
    requests.post(f"{BASE}/api/batches", json={
        "batch_no": "TF-SEALED-01",
        "reagent_name": "封存调拨测试",
        "total_quantity": 5,
        "expiry_date": "2027-01-01",
        "location_code": "TF-SEALED-LOC",
        "username": "bob"
    })
    requests.post(f"{BASE}/api/batches/TF-SEALED-01/pickup", json={
        "username": "alice", "quantity": 1
    })
    requests.post(f"{BASE}/api/batches/TF-SEALED-01/return", json={
        "username": "alice", "quantity": 1
    })
    requests.post(f"{BASE}/api/batches/TF-SEALED-01/seal", json={
        "username": "charlie"
    })
    resp = requests.post(f"{BASE}/api/batches/TF-SEALED-01/transfer", json={
        "username": "charlie",
        "to_location_code": "A-01"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '封存'", "封存" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("19.6 冲突失败时数据不修改")
    resp = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    batch_final = resp.json()
    check("冲突后批次仍在 A-01", batch_final["location_name"] == "冷藏柜A-01", f"实际: {batch_final['location_name']}")
    resp = requests.get(f"{BASE}/api/locations/A-01")
    a01_final = resp.json()
    resp = requests.get(f"{BASE}/api/locations/B-01")
    b01_final = resp.json()
    print(f"  A-01 used={a01_final['used']}, B-01 used={b01_final['used']}")
    check("库位计数与成功调拨后一致", a01_final["used"] == a01_after["used"] and b01_final["used"] == b01_after["used"])

    section("20. 保存调拨重启前状态")
    with open("batch_transfer_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(batch_final, f, ensure_ascii=False, indent=2)
    transfer_loc_state = {
        "A-01": a01_final,
        "B-01": b01_final
    }
    with open("transfer_locations_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(transfer_loc_state, f, ensure_ascii=False, indent=2)

    section("21. 温控巡检 - reviewer 配置库位温控监控")
    resp = requests.post(f"{BASE}/api/locations/A-01/temp-config", json={
        "username": "charlie",
        "monitoring_enabled": True,
        "temp_min": 2.0,
        "temp_max": 8.0
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("monitoring_enabled 为 True", d.get("monitoring_enabled") == True, f"实际: {d.get('monitoring_enabled')}")
    check("temp_min 为 2.0", d.get("temp_min") == 2.0, f"实际: {d.get('temp_min')}")
    check("temp_max 为 8.0", d.get("temp_max") == 8.0, f"实际: {d.get('temp_max')}")

    section("21.1 温控配置写入库位日志")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-01", "action": "TEMP_CONFIG"})
    d = resp.json()
    check("存在 TEMP_CONFIG 日志", d["total"] >= 1, f"实际: {d['total']}")
    if d["items"]:
        log = d["items"][0]
        check("TEMP_CONFIG 操作人是 charlie", log["username"] == "charlie")
        check("TEMP_CONFIG 操作人角色是 reviewer", log["user_role"] == "reviewer")
        check("TEMP_CONFIG 备注含 '启用'", "启用" in (log.get("remark") or ""))

    section("22. 温控巡检 - operator 提交正常巡检记录")
    resp = requests.post(f"{BASE}/api/locations/A-01/temperature-inspections", json={
        "username": "alice",
        "temperature": 4.5,
        "inspection_date": "2026-06-13",
        "remark": "上午巡检，温度正常"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("temperature 为 4.5", d.get("temperature") == 4.5, f"实际: {d.get('temperature')}")
    check("location_code 为 A-01", d.get("location_code") == "A-01")
    check("username 为 alice", d.get("username") == "alice")
    check("user_role 为 operator", d.get("user_role") == "operator")
    check("inspection_date 为 2026-06-13", d.get("inspection_date") == "2026-06-13")
    check("remark 正确", d.get("remark") == "上午巡检，温度正常")
    normal_insp_id = d.get("id")

    section("22.1 正常巡检写入库位日志")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-01", "action": "TEMP_INSPECT"})
    d = resp.json()
    check("存在 TEMP_INSPECT 日志", d["total"] >= 1, f"实际: {d['total']}")
    if d["items"]:
        log = d["items"][0]
        check("TEMP_INSPECT 备注含温度", "4.5" in (log.get("remark") or ""))

    section("23. 温控巡检 - 超温巡检自动生成异常单")
    resp = requests.post(f"{BASE}/api/locations/A-01/temperature-inspections", json={
        "username": "bob",
        "temperature": 10.5,
        "inspection_date": "2026-06-13",
        "remark": "温度偏高"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
    check("temperature 为 10.5", d.get("temperature") == 10.5)
    check("username 为 bob", d.get("username") == "bob")
    overtemp_insp_id = d.get("id")

    section("23.1 超温后异常单已自动生成")
    resp = requests.get(f"{BASE}/api/temperature-alerts", params={"location_code": "A-01", "status": "OPEN"})
    d = resp.json()
    print(f"  OPEN 异常单数: {d['total']}")
    check("存在至少 1 条 OPEN 异常单", d["total"] >= 1, f"实际: {d['total']}")
    if d["items"]:
        alert = d["items"][0]
        check("异常单温度为 10.5", alert["temperature"] == 10.5)
        check("异常单 temp_min 为 2.0", alert["temp_min"] == 2.0)
        check("异常单 temp_max 为 8.0", alert["temp_max"] == 8.0)
        check("异常单状态为 OPEN", alert["status"] == "OPEN")
        check("异常单 location_code 为 A-01", alert["location_code"] == "A-01")
        alert_id = alert["id"]
    else:
        alert_id = None

    section("23.2 超温巡检写入 TEMP_INSPECT 和 TEMP_ALERT 日志")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-01", "action": "TEMP_ALERT"})
    d = resp.json()
    check("存在 TEMP_ALERT 日志", d["total"] >= 1, f"实际: {d['total']}")
    if d["items"]:
        log = d["items"][0]
        check("TEMP_ALERT 备注含 '异常'", "异常" in (log.get("remark") or ""))

    section("24. 温控巡检 - reviewer 处理异常单")
    if alert_id:
        resp = requests.post(f"{BASE}/api/temperature-alerts/{alert_id}/handle", json={
            "username": "charlie",
            "reason": "冷柜门未关紧导致温度升高",
            "disposal": "已关紧柜门，温度已恢复正常"
        })
        d = resp.json()
        print(f"  HTTP {resp.status_code}")
        check("状态码 200", resp.status_code == 200, f"实际: {resp.status_code}, 详情: {d.get('detail')}")
        check("状态变为 HANDLED", d.get("status") == "HANDLED", f"实际: {d.get('status')}")
        check("handler_name 为 charlie", d.get("handler_name") == "charlie")
        check("reason 正确", d.get("reason") == "冷柜门未关紧导致温度升高")
        check("disposal 正确", d.get("disposal") == "已关紧柜门，温度已恢复正常")
        check("handled_at 非空", d.get("handled_at") is not None)
    else:
        check("跳过异常单处理（无 OPEN 异常单）", False, "前置步骤未产生异常单")

    section("24.1 异常处理写入库位日志")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-01", "action": "TEMP_ALERT_HANDLE"})
    d = resp.json()
    check("存在 TEMP_ALERT_HANDLE 日志", d["total"] >= 1, f"实际: {d['total']}")
    if d["items"]:
        log = d["items"][0]
        check("TEMP_ALERT_HANDLE 操作人是 charlie", log["username"] == "charlie")
        check("TEMP_ALERT_HANDLE 备注含 '处置'", "处置" in (log.get("remark") or ""))

    section("25. 温控巡检 - 查询巡检记录")
    resp = requests.get(f"{BASE}/api/locations/A-01/temperature-inspections")
    d = resp.json()
    print(f"  A-01 巡检记录数: {d['total']}")
    check("至少有 2 条巡检记录", d["total"] >= 2, f"实际: {d['total']}")

    section("25.1 按日期查询巡检记录")
    resp = requests.get(f"{BASE}/api/temperature-inspections", params={"inspection_date": "2026-06-13"})
    d = resp.json()
    print(f"  2026-06-13 巡检记录数: {d['total']}")
    check("至少有 2 条记录", d["total"] >= 2, f"实际: {d['total']}")

    section("25.2 按提交人查询巡检记录")
    resp = requests.get(f"{BASE}/api/temperature-inspections", params={"username": "alice"})
    d = resp.json()
    print(f"  alice 的巡检记录数: {d['total']}")
    check("alice 至少 1 条巡检记录", d["total"] >= 1, f"实际: {d['total']}")
    if d["items"]:
        check("alice 的记录都来自 alice", all(item["username"] == "alice" for item in d["items"]))

    section("26. 温控巡检 - 导出巡检和异常记录")
    resp = requests.get(f"{BASE}/api/export/temperature", params={"location_code": "A-01"})
    export_data = resp.json()
    print(f"  巡检记录数: {export_data['inspections']['total']}, 异常单数: {export_data['alerts']['total']}")
    check("导出有 inspections 字段", "inspections" in export_data)
    check("导出有 alerts 字段", "alerts" in export_data)
    check("导出巡检记录数 >= 2", export_data["inspections"]["total"] >= 2, f"实际: {export_data['inspections']['total']}")
    check("导出异常单数 >= 1", export_data["alerts"]["total"] >= 1, f"实际: {export_data['alerts']['total']}")
    check("导出巡检每条有 operator", all(r.get("operator") for r in export_data["inspections"]["records"]))
    check("导出巡检每条有 temperature", all(r.get("temperature") is not None for r in export_data["inspections"]["records"]))
    check("导出异常单有 status 字段", all(r.get("status") for r in export_data["alerts"]["records"]))

    with open("temperature_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print("  已保存 temperature_before_restart.json")

    section("27. 温控巡检 - 失败路径：operator 配置监控（权限不足）")
    resp = requests.post(f"{BASE}/api/locations/A-01/temp-config", json={
        "username": "alice",
        "monitoring_enabled": True,
        "temp_min": 2.0,
        "temp_max": 8.0
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 403", resp.status_code == 403, f"实际: {resp.status_code}")
    check("错误信息含 '权限'", "权限" in d.get("detail", ""))

    section("27.1 验证配置未改变")
    resp = requests.get(f"{BASE}/api/locations/A-01")
    loc_check = resp.json()
    check("temp_min 仍为 2.0", loc_check["temp_min"] == 2.0, f"实际: {loc_check['temp_min']}")
    check("temp_max 仍为 8.0", loc_check["temp_max"] == 8.0, f"实际: {loc_check['temp_max']}")

    section("28. 温控巡检 - 失败路径：未启用监控的库位提交巡检")
    resp = requests.get(f"{BASE}/api/locations/B-01")
    b01_loc = resp.json()
    print(f"  B-01 monitoring_enabled={b01_loc.get('monitoring_enabled')}")
    resp = requests.post(f"{BASE}/api/locations/B-01/temperature-inspections", json={
        "username": "alice",
        "temperature": 25.0,
        "inspection_date": "2026-06-13"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '未启用'", "未启用" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("29. 温控巡检 - 失败路径：温度格式非法")
    resp = requests.post(f"{BASE}/api/locations/A-01/temperature-inspections", json={
        "username": "alice",
        "temperature": "abc",
        "inspection_date": "2026-06-13"
    })
    print(f"  HTTP {resp.status_code}")
    check("温度非法返回 422", resp.status_code == 422, f"实际: {resp.status_code}")

    section("30. 温控巡检 - 失败路径：重复巡检（同用户同库位同日期）")
    resp = requests.post(f"{BASE}/api/locations/A-01/temperature-inspections", json={
        "username": "alice",
        "temperature": 5.0,
        "inspection_date": "2026-06-13"
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 409", resp.status_code == 409, f"实际: {resp.status_code}")
    check("错误信息含 '重复' 或 '已'", "已" in d.get("detail", "") or "重复" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("31. 温控巡检 - 失败路径：operator 处理异常单（权限不足）")
    if alert_id:
        resp = requests.post(f"{BASE}/api/temperature-alerts/{alert_id}/handle", json={
            "username": "alice",
            "reason": "越权测试",
            "disposal": "越权测试"
        })
        d = resp.json()
        print(f"  HTTP {resp.status_code}")
        check("状态码 403", resp.status_code == 403, f"实际: {resp.status_code}")
        check("错误信息含 '权限'", "权限" in d.get("detail", ""))
    else:
        check("跳过（无异常单）", False, "前置步骤未产生异常单")

    section("32. 温控巡检 - 失败路径：启用监控但未设温度范围")
    resp = requests.get(f"{BASE}/api/locations/B-01")
    b01_check = resp.json()
    resp = requests.post(f"{BASE}/api/locations/B-01/temp-config", json={
        "username": "charlie",
        "monitoring_enabled": True
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '必须设置'", "必须设置" in d.get("detail", "") or "最低温度" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("32.1 失败后 B-01 监控状态未改变")
    resp = requests.get(f"{BASE}/api/locations/B-01")
    b01_after = resp.json()
    check("B-01 monitoring_enabled 未变", b01_after["monitoring_enabled"] == b01_check["monitoring_enabled"])

    section("33. 温控巡检 - 失败路径：最低温度 >= 最高温度")
    resp = requests.post(f"{BASE}/api/locations/A-01/temp-config", json={
        "username": "charlie",
        "monitoring_enabled": True,
        "temp_min": 8.0,
        "temp_max": 2.0
    })
    d = resp.json()
    print(f"  HTTP {resp.status_code}")
    check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
    check("错误信息含 '小于'", "小于" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("34. 温控巡检 - 失败路径：已处理的异常单不能再次处理")
    if alert_id:
        resp = requests.post(f"{BASE}/api/temperature-alerts/{alert_id}/handle", json={
            "username": "charlie",
            "reason": "再次处理",
            "disposal": "再次处理"
        })
        d = resp.json()
        print(f"  HTTP {resp.status_code}")
        check("状态码 400", resp.status_code == 400, f"实际: {resp.status_code}")
        check("错误信息含 'OPEN'", "OPEN" in d.get("detail", ""), f"实际: {d.get('detail')}")

    section("35. 温控巡检 - 保存重启前状态")
    resp = requests.get(f"{BASE}/api/locations/A-01")
    temp_loc_before = resp.json()
    with open("temp_location_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(temp_loc_before, f, ensure_ascii=False, indent=2)

    resp = requests.get(f"{BASE}/api/temperature-alerts", params={"location_code": "A-01"})
    temp_alerts_before = resp.json()
    with open("temp_alerts_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(temp_alerts_before, f, ensure_ascii=False, indent=2)

    section("15. 记录重启前状态（用于重启后比对）")
    resp = requests.get(f"{BASE}/api/batches/REG-TEST-001")
    before = resp.json()
    print(f"  批次: {before['batch_no']}, 状态: {before['status']}, 可用: {before['available_quantity']}")
    with open("batch_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(before, f, ensure_ascii=False, indent=2)

    resp = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    before2 = resp.json()
    with open("batch2_before_restart.json", "w", encoding="utf-8") as f:
        json.dump(before2, f, ensure_ascii=False, indent=2)

    section("测试第一阶段总结")
    print(f"  通过: {passed}, 失败: {failed}")
    if failed > 0:
        print("  [X] 存在失败用例，停止测试")
        return 1
    else:
        print("  [OK] 第一阶段全部通过，请重启服务后运行 --restart-check 验证持久化")
        print("  已保存: export_before_restart.json, batch_before_restart.json, batch2_before_restart.json")
        return 0


def run_restart_checks():
    global passed, failed
    passed = 0
    failed = 0

    section("15. 重启后 - 批次状态一致性")
    with open("batch_before_restart.json", "r", encoding="utf-8") as f:
        before = json.load(f)
    resp = requests.get(f"{BASE}/api/batches/REG-TEST-001")
    after = resp.json()
    print(f"  重启前: status={before['status']}, available={before['available_quantity']}")
    print(f"  重启后: status={after['status']}, available={after['available_quantity']}")
    check("状态一致", before["status"] == after["status"], f"{before['status']} vs {after['status']}")
    check("可用数量一致", before["available_quantity"] == after["available_quantity"])

    with open("batch2_before_restart.json", "r", encoding="utf-8") as f:
        before2 = json.load(f)
    resp = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    after2 = resp.json()
    check("未受影响批次状态仍为 REGISTERED", after2["status"] == "REGISTERED", f"实际: {after2['status']}")
    check("未受影响批次库存仍为 50", after2["available_quantity"] == 50, f"实际: {after2['available_quantity']}")

    section("16. 重启后 - 审计历史一致性")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"batch_no": "REG-TEST-001"})
    d = resp.json()
    print(f"  重启后审计记录数: {d['total']}")
    check("审计记录数仍为 4", d["total"] == 4, f"实际: {d['total']}")
    actions = sorted([log["action"] for log in d["items"]])
    check("动作列表完整", actions == sorted(["REGISTER", "PICKUP", "RETURN", "SEAL"]), f"实际: {actions}")

    reg_log = None
    for log in d["items"]:
        if log["action"] == "REGISTER":
            reg_log = log
            break
    check("REGISTER 登记人 bob 仍存在", reg_log is not None and reg_log.get("username") == "bob")
    check("REGISTER 角色 operator 仍存在", reg_log is not None and reg_log.get("user_role") == "operator")
    check("REGISTER 建档备注仍存在", reg_log is not None and "采购入库" in (reg_log.get("remark") or ""))

    section("17. 重启后 - 导出内容一致性")
    with open("export_before_restart.json", "r", encoding="utf-8") as f:
        before_export = json.load(f)

    resp = requests.get(f"{BASE}/api/export/audit", params={"batch_no": "REG-TEST-001"})
    after_export = resp.json()

    print(f"  重启前导出 total: {before_export['total']}")
    print(f"  重启后导出 total: {after_export['total']}")
    check("导出记录数一致", before_export["total"] == after_export["total"])

    before_actions = sorted([r["action"] for r in before_export["records"]])
    after_actions = sorted([r["action"] for r in after_export["records"]])
    check("导出动作列表一致", before_actions == after_actions, f"{before_actions} vs {after_actions}")

    before_reg = [r for r in before_export["records"] if r["action"] == "REGISTER"][0]
    after_reg = [r for r in after_export["records"] if r["action"] == "REGISTER"][0]
    check("导出 REGISTER 的 operator 一致", before_reg["operator"] == after_reg["operator"])
    check("导出 REGISTER 的 operator_role 一致", before_reg["operator_role"] == after_reg["operator_role"])
    check("导出 REGISTER 的备注一致", before_reg.get("remark") == after_reg.get("remark"))
    check("导出 REGISTER 的数量一致", before_reg["quantity"] == after_reg["quantity"])

    section("18. 重启后 - 库位冻结状态一致性")
    with open("location_before_restart.json", "r", encoding="utf-8") as f:
        loc_before = json.load(f)
    resp = requests.get(f"{BASE}/api/locations/A-02")
    loc_after = resp.json()
    print(f"  重启前: frozen={loc_before['frozen']}, used={loc_before['used']}")
    print(f"  重启后: frozen={loc_after['frozen']}, used={loc_after['used']}")
    check("冻结状态一致", loc_before["frozen"] == loc_after["frozen"], f"{loc_before['frozen']} vs {loc_after['frozen']}")
    check("已用数量一致", loc_before["used"] == loc_after["used"], f"{loc_before['used']} vs {loc_after['used']}")

    section("19. 重启后 - 库位操作日志一致性")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-02"})
    d = resp.json()
    print(f"  重启后 A-02 库位日志数: {d['total']}")
    check("库位日志数 >= 3（冻结、解冻、再冻结）", d["total"] >= 3, f"实际: {d['total']}")
    actions = [log["action"] for log in d["items"]]
    print(f"  动作序列: {actions}")
    check("包含 FREEZE 动作", "FREEZE" in actions)
    check("包含 UNFREEZE 动作", "UNFREEZE" in actions)
    check("操作人都是 charlie", all(log["username"] == "charlie" for log in d["items"]))
    check("操作人角色都是 reviewer", all(log["user_role"] == "reviewer" for log in d["items"]))

    section("20. 重启后 - 库位日志导出一致性")
    with open("location_log_before_restart.json", "r", encoding="utf-8") as f:
        before_loc_export = json.load(f)
    resp = requests.get(f"{BASE}/api/export/location-logs", params={"location_code": "A-02"})
    after_loc_export = resp.json()
    print(f"  重启前导出 total: {before_loc_export['total']}")
    print(f"  重启后导出 total: {after_loc_export['total']}")
    check("库位日志导出记录数一致（重启后又多了一次冻结，所以重启后应该更多）",
          after_loc_export["total"] >= before_loc_export["total"])

    section("21. 重启后 - 冻结库位上的批次状态一致")
    resp = requests.get(f"{BASE}/api/batches/FREEZE-TEST-002")
    batch_after = resp.json()
    print(f"  FREEZE-TEST-002 状态: {batch_after['status']}, 可用: {batch_after['available_quantity']}")
    check("批次状态仍为 IN_USE", batch_after["status"] == "IN_USE", f"实际: {batch_after['status']}")
    check("可用数量仍为 12", batch_after["available_quantity"] == 12, f"实际: {batch_after['available_quantity']}")

    section("22. 重启后 - 调拨批次位置一致")
    with open("batch_transfer_before_restart.json", "r", encoding="utf-8") as f:
        batch_transfer_before = json.load(f)
    resp = requests.get(f"{BASE}/api/batches/REAG-2026-0002")
    batch_transfer_after = resp.json()
    print(f"  重启前: location={batch_transfer_before['location_name']}")
    print(f"  重启后: location={batch_transfer_after['location_name']}")
    check("调拨后批次位置仍为 A-01", batch_transfer_after["location_name"] == "冷藏柜A-01",
          f"实际: {batch_transfer_after['location_name']}")
    check("批次位置一致", batch_transfer_before["location_name"] == batch_transfer_after["location_name"])

    section("23. 重启后 - 调拨源库位和目标库位 used 计数一致")
    with open("transfer_locations_before_restart.json", "r", encoding="utf-8") as f:
        transfer_loc_before = json.load(f)
    resp = requests.get(f"{BASE}/api/locations/A-01")
    a01_after = resp.json()
    resp = requests.get(f"{BASE}/api/locations/B-01")
    b01_after = resp.json()
    print(f"  A-01: 重启前 used={transfer_loc_before['A-01']['used']}, 重启后 used={a01_after['used']}")
    print(f"  B-01: 重启前 used={transfer_loc_before['B-01']['used']}, 重启后 used={b01_after['used']}")
    check("A-01 used 计数一致", transfer_loc_before["A-01"]["used"] == a01_after["used"])
    check("B-01 used 计数一致", transfer_loc_before["B-01"]["used"] == b01_after["used"])

    section("24. 重启后 - 调拨记录一致")
    resp = requests.get(f"{BASE}/api/transfers", params={"batch_no": "REAG-2026-0002"})
    d = resp.json()
    print(f"  重启后 REAG-2026-0002 调拨记录数: {d['total']}")
    check("调拨记录仍存在", d["total"] >= 1)
    if d["items"]:
        t = d["items"][0]
        check("from_location_code = B-01", t["from_location_code"] == "B-01")
        check("to_location_code = A-01", t["to_location_code"] == "A-01")
        check("操作人是 charlie", t["username"] == "charlie")

    section("25. 重启后 - 调拨导出一致")
    with open("transfers_before_restart.json", "r", encoding="utf-8") as f:
        transfer_export_before = json.load(f)
    resp = requests.get(f"{BASE}/api/export/transfers", params={"batch_no": "REAG-2026-0002"})
    transfer_export_after = resp.json()
    print(f"  重启前调拨导出 total: {transfer_export_before['total']}")
    print(f"  重启后调拨导出 total: {transfer_export_after['total']}")
    check("调拨导出记录数一致", transfer_export_before["total"] == transfer_export_after["total"])
    if transfer_export_after["records"]:
        r = transfer_export_after["records"][0]
        check("导出 batch_no 一致", r["batch_no"] == "REAG-2026-0002")
        check("导出 from_location_code 一致", r["from_location_code"] == "B-01")
        check("导出 to_location_code 一致", r["to_location_code"] == "A-01")

    section("26. 重启后 - 调拨审计和库位日志一致")
    resp = requests.get(f"{BASE}/api/audit-logs", params={"batch_no": "REAG-2026-0002"})
    d = resp.json()
    transfer_logs = [log for log in d["items"] if log["action"] == "TRANSFER"]
    check("TRANSFER 审计日志仍存在", len(transfer_logs) >= 1)

    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "B-01"})
    d = resp.json()
    b01_out = [log for log in d["items"] if log["action"] == "TRANSFER_OUT"]
    check("B-01 TRANSFER_OUT 日志仍存在", len(b01_out) >= 1)

    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-01"})
    d = resp.json()
    a01_in = [log for log in d["items"] if log["action"] == "TRANSFER_IN"]
    check("A-01 TRANSFER_IN 日志仍存在", len(a01_in) >= 1)

    section("27. 重启后 - 温控监控配置一致")
    with open("temp_location_before_restart.json", "r", encoding="utf-8") as f:
        temp_loc_before = json.load(f)
    resp = requests.get(f"{BASE}/api/locations/A-01")
    temp_loc_after = resp.json()
    print(f"  重启前: monitoring_enabled={temp_loc_before['monitoring_enabled']}, temp_min={temp_loc_before.get('temp_min')}, temp_max={temp_loc_before.get('temp_max')}")
    print(f"  重启后: monitoring_enabled={temp_loc_after['monitoring_enabled']}, temp_min={temp_loc_after.get('temp_min')}, temp_max={temp_loc_after.get('temp_max')}")
    check("monitoring_enabled 一致", temp_loc_before["monitoring_enabled"] == temp_loc_after["monitoring_enabled"])
    check("temp_min 一致", temp_loc_before["temp_min"] == temp_loc_after["temp_min"])
    check("temp_max 一致", temp_loc_before["temp_max"] == temp_loc_after["temp_max"])

    section("28. 重启后 - 巡检记录一致")
    resp = requests.get(f"{BASE}/api/locations/A-01/temperature-inspections")
    d = resp.json()
    print(f"  巡检记录数: {d['total']}")
    check("巡检记录数 >= 2", d["total"] >= 2, f"实际: {d['total']}")
    temps = [insp["temperature"] for insp in d["items"]]
    print(f"  温度列表: {temps}")
    check("巡检包含 4.5°C 记录", 4.5 in temps, f"实际: {temps}")
    check("巡检包含 10.5°C 记录", 10.5 in temps, f"实际: {temps}")

    section("29. 重启后 - 异常单处理状态一致")
    with open("temp_alerts_before_restart.json", "r", encoding="utf-8") as f:
        temp_alerts_before = json.load(f)
    resp = requests.get(f"{BASE}/api/temperature-alerts", params={"location_code": "A-01"})
    temp_alerts_after = resp.json()
    print(f"  重启前异常单数: {temp_alerts_before['total']}, 重启后: {temp_alerts_after['total']}")
    check("异常单数一致", temp_alerts_before["total"] == temp_alerts_after["total"], f"重启前: {temp_alerts_before['total']}, 重启后: {temp_alerts_after['total']}")
    before_statuses = sorted([a["status"] for a in temp_alerts_before["items"]])
    after_statuses = sorted([a["status"] for a in temp_alerts_after["items"]])
    check("异常单状态列表一致", before_statuses == after_statuses, f"重启前: {before_statuses}, 重启后: {after_statuses}")

    handled_alerts = [a for a in temp_alerts_after["items"] if a["status"] == "HANDLED"]
    if handled_alerts:
        ha = handled_alerts[0]
        check("已处理异常单有 handler_name", ha.get("handler_name") is not None)
        check("已处理异常单有 reason", ha.get("reason") is not None)
        check("已处理异常单有 disposal", ha.get("disposal") is not None)
        check("已处理异常单有 handled_at", ha.get("handled_at") is not None)

    section("30. 重启后 - 温控巡检导出一致")
    with open("temperature_before_restart.json", "r", encoding="utf-8") as f:
        temp_export_before = json.load(f)
    resp = requests.get(f"{BASE}/api/export/temperature", params={"location_code": "A-01"})
    temp_export_after = resp.json()
    print(f"  重启前巡检导出: {temp_export_before['inspections']['total']}, 重启后: {temp_export_after['inspections']['total']}")
    check("导出巡检记录数一致", temp_export_before["inspections"]["total"] == temp_export_after["inspections"]["total"])
    check("导出异常单数一致", temp_export_before["alerts"]["total"] == temp_export_after["alerts"]["total"])
    before_insp_temps = sorted([r["temperature"] for r in temp_export_before["inspections"]["records"]])
    after_insp_temps = sorted([r["temperature"] for r in temp_export_after["inspections"]["records"]])
    check("导出巡检温度列表一致", before_insp_temps == after_insp_temps, f"重启前: {before_insp_temps}, 重启后: {after_insp_temps}")

    section("31. 重启后 - 温控库位日志一致")
    resp = requests.get(f"{BASE}/api/location-logs", params={"location_code": "A-01"})
    d = resp.json()
    temp_actions = [log["action"] for log in d["items"] if log["action"].startswith("TEMP_")]
    print(f"  温控相关日志动作: {temp_actions}")
    check("包含 TEMP_CONFIG", "TEMP_CONFIG" in temp_actions)
    check("包含 TEMP_INSPECT", "TEMP_INSPECT" in temp_actions)
    check("包含 TEMP_ALERT", "TEMP_ALERT" in temp_actions)
    check("包含 TEMP_ALERT_HANDLE", "TEMP_ALERT_HANDLE" in temp_actions)

    section("重启后验证总结")
    print(f"  通过: {passed}, 失败: {failed}")
    for f in ["export_before_restart.json", "batch_before_restart.json", "batch2_before_restart.json",
              "location_before_restart.json", "location_log_before_restart.json",
              "transfers_before_restart.json", "batch_transfer_before_restart.json",
              "transfer_locations_before_restart.json",
              "temperature_before_restart.json", "temp_location_before_restart.json",
              "temp_alerts_before_restart.json"]:
        try:
            os.remove(f)
        except:
            pass
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--restart-check":
        sys.exit(run_restart_checks())
    else:
        sys.exit(run_phase1())
