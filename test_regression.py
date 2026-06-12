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

    section("14. 记录重启前状态（用于重启后比对）")
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

    section("重启后验证总结")
    print(f"  通过: {passed}, 失败: {failed}")
    for f in ["export_before_restart.json", "batch_before_restart.json", "batch2_before_restart.json"]:
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
