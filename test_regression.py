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

    section("重启后验证总结")
    print(f"  通过: {passed}, 失败: {failed}")
    for f in ["export_before_restart.json", "batch_before_restart.json", "batch2_before_restart.json",
              "location_before_restart.json", "location_log_before_restart.json"]:
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
