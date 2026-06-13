from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Optional, List
import json

from database import engine, get_db, Base
import models
import schemas

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="试剂留样交接系统 API",
    description="试剂留样登记、领取、归还、封存、报废全流程管理",
    version="1.0.0"
)


ROLE_OPERATOR = "operator"
ROLE_REVIEWER = "reviewer"

STATUS_REGISTERED = "REGISTERED"
STATUS_IN_USE = "IN_USE"
STATUS_PENDING_REVIEW = "PENDING_REVIEW"
STATUS_SEALED = "SEALED"
STATUS_SCRAPPED = "SCRAPPED"

ACTION_REGISTER = "REGISTER"
ACTION_PICKUP = "PICKUP"
ACTION_RETURN = "RETURN"
ACTION_SEAL = "SEAL"
ACTION_SCRAP = "SCRAP"

ACTION_LOCATION_FREEZE = "FREEZE"
ACTION_LOCATION_UNFREEZE = "UNFREEZE"

ACTION_TRANSFER = "TRANSFER"
ACTION_LOCATION_TRANSFER_OUT = "TRANSFER_OUT"
ACTION_LOCATION_TRANSFER_IN = "TRANSFER_IN"

ACTION_TEMP_CONFIG = "TEMP_CONFIG"
ACTION_TEMP_INSPECT = "TEMP_INSPECT"
ACTION_TEMP_ALERT = "TEMP_ALERT"
ACTION_TEMP_ALERT_HANDLE = "TEMP_ALERT_HANDLE"


def get_user_or_404(db: Session, username: str) -> models.User:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"用户 {username} 不存在")
    return user


def get_batch_or_404(db: Session, batch_no: str) -> models.Batch:
    batch = db.query(models.Batch).filter(models.Batch.batch_no == batch_no).first()
    if not batch:
        raise HTTPException(status_code=404, detail=f"批次 {batch_no} 不存在")
    return batch


def get_location_or_404(db: Session, code: str) -> models.Location:
    location = db.query(models.Location).filter(models.Location.code == code).first()
    if not location:
        raise HTTPException(status_code=404, detail=f"库位 {code} 不存在")
    return location


def require_role(user: models.User, allowed_roles: list):
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"权限不足：用户 {user.username} 角色为 {user.role}，需要 {' 或 '.join(allowed_roles)} 角色"
        )


def add_audit_log(db: Session, batch_id: int, user_id: int, action: str,
                  quantity: int = 0, from_status: Optional[str] = None,
                  to_status: Optional[str] = None, remark: Optional[str] = None):
    log = models.AuditLog(
        batch_id=batch_id,
        user_id=user_id,
        action=action,
        quantity=quantity,
        from_status=from_status,
        to_status=to_status,
        remark=remark
    )
    db.add(log)


def batch_to_response(batch: models.Batch) -> schemas.BatchResponse:
    return schemas.BatchResponse(
        id=batch.id,
        batch_no=batch.batch_no,
        reagent_name=batch.reagent_name,
        total_quantity=batch.total_quantity,
        available_quantity=batch.available_quantity,
        expiry_date=batch.expiry_date,
        location_id=batch.location_id,
        location_name=batch.location.name if batch.location else None,
        status=batch.status,
        created_at=batch.created_at,
        updated_at=batch.updated_at
    )


def audit_log_to_response(log: models.AuditLog) -> schemas.AuditLogResponse:
    return schemas.AuditLogResponse(
        id=log.id,
        batch_id=log.batch_id,
        batch_no=log.batch.batch_no if log.batch else None,
        user_id=log.user_id,
        username=log.user.username if log.user else None,
        user_role=log.user.role if log.user else None,
        action=log.action,
        quantity=log.quantity,
        from_status=log.from_status,
        to_status=log.to_status,
        remark=log.remark,
        created_at=log.created_at
    )


def add_location_log(db: Session, location_id: int, user_id: int, action: str,
                     remark: Optional[str] = None):
    log = models.LocationLog(
        location_id=location_id,
        user_id=user_id,
        action=action,
        remark=remark
    )
    db.add(log)


def location_log_to_response(log: models.LocationLog) -> schemas.LocationLogResponse:
    return schemas.LocationLogResponse(
        id=log.id,
        location_id=log.location_id,
        location_code=log.location.code if log.location else None,
        user_id=log.user_id,
        username=log.user.username if log.user else None,
        user_role=log.user.role if log.user else None,
        action=log.action,
        remark=log.remark,
        created_at=log.created_at
    )


def transfer_to_response(transfer: models.BatchTransfer) -> schemas.BatchTransferResponse:
    return schemas.BatchTransferResponse(
        id=transfer.id,
        batch_id=transfer.batch_id,
        batch_no=transfer.batch.batch_no if transfer.batch else None,
        from_location_id=transfer.from_location_id,
        from_location_code=transfer.from_location.code if transfer.from_location else None,
        to_location_id=transfer.to_location_id,
        to_location_code=transfer.to_location.code if transfer.to_location else None,
        user_id=transfer.user_id,
        username=transfer.user.username if transfer.user else None,
        user_role=transfer.user.role if transfer.user else None,
        remark=transfer.remark,
        created_at=transfer.created_at
    )


def inspection_to_response(insp: models.TemperatureInspection) -> schemas.TemperatureInspectionResponse:
    return schemas.TemperatureInspectionResponse(
        id=insp.id,
        location_id=insp.location_id,
        location_code=insp.location.code if insp.location else None,
        user_id=insp.user_id,
        username=insp.user.username if insp.user else None,
        user_role=insp.user.role if insp.user else None,
        temperature=insp.temperature,
        inspection_date=insp.inspection_date.isoformat() if insp.inspection_date else None,
        remark=insp.remark,
        created_at=insp.created_at
    )


def alert_to_response(alert: models.TemperatureAlert) -> schemas.TemperatureAlertResponse:
    return schemas.TemperatureAlertResponse(
        id=alert.id,
        location_id=alert.location_id,
        location_code=alert.location.code if alert.location else None,
        inspection_id=alert.inspection_id,
        temperature=alert.temperature,
        temp_min=alert.temp_min,
        temp_max=alert.temp_max,
        status=alert.status,
        handler_id=alert.handler_id,
        handler_name=alert.handler.username if alert.handler else None,
        reason=alert.reason,
        disposal=alert.disposal,
        handled_at=alert.handled_at,
        created_at=alert.created_at
    )


def migrate_db():
    from sqlalchemy import text
    db = next(get_db())
    try:
        db.execute(text("ALTER TABLE locations ADD COLUMN frozen BOOLEAN DEFAULT 0 NOT NULL"))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS location_logs (
                id INTEGER PRIMARY KEY,
                location_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action VARCHAR(50) NOT NULL,
                remark TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS batch_transfers (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL,
                from_location_id INTEGER NOT NULL,
                to_location_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                remark TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches (id),
                FOREIGN KEY (from_location_id) REFERENCES locations (id),
                FOREIGN KEY (to_location_id) REFERENCES locations (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(text("ALTER TABLE locations ADD COLUMN monitoring_enabled BOOLEAN DEFAULT 0 NOT NULL"))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(text("ALTER TABLE locations ADD COLUMN temp_min FLOAT"))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(text("ALTER TABLE locations ADD COLUMN temp_max FLOAT"))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS temperature_inspections (
                id INTEGER PRIMARY KEY,
                location_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                temperature FLOAT NOT NULL,
                inspection_date DATE NOT NULL,
                remark TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS temperature_alerts (
                id INTEGER PRIMARY KEY,
                location_id INTEGER NOT NULL,
                inspection_id INTEGER NOT NULL,
                temperature FLOAT NOT NULL,
                temp_min FLOAT,
                temp_max FLOAT,
                status VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
                handler_id INTEGER,
                reason TEXT,
                disposal TEXT,
                handled_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations (id),
                FOREIGN KEY (inspection_id) REFERENCES temperature_inspections (id),
                FOREIGN KEY (handler_id) REFERENCES users (id)
            )
        """))
        db.commit()
    except Exception:
        db.rollback()
    db.close()


def init_sample_data():
    db = next(get_db())

    if db.query(models.User).count() == 0:
        users = [
            models.User(username="alice", role=ROLE_OPERATOR),
            models.User(username="bob", role=ROLE_OPERATOR),
            models.User(username="charlie", role=ROLE_REVIEWER),
        ]
        db.add_all(users)
        db.commit()

    if db.query(models.Location).count() == 0:
        locations = [
            models.Location(code="A-01", name="冷藏柜A-01", capacity=50),
            models.Location(code="A-02", name="冷藏柜A-02", capacity=30),
            models.Location(code="B-01", name="常温柜B-01", capacity=100),
        ]
        db.add_all(locations)
        db.commit()

    if db.query(models.Batch).count() == 0:
        loc_a01 = db.query(models.Location).filter(models.Location.code == "A-01").first()
        loc_b01 = db.query(models.Location).filter(models.Location.code == "B-01").first()

        batches = [
            models.Batch(
                batch_no="REAG-2026-0001",
                reagent_name="PCR反应试剂盒",
                total_quantity=20,
                available_quantity=20,
                expiry_date="2027-06-01",
                location_id=loc_a01.id,
                status=STATUS_REGISTERED
            ),
            models.Batch(
                batch_no="REAG-2026-0002",
                reagent_name="抗原检测试剂",
                total_quantity=50,
                available_quantity=50,
                expiry_date="2026-12-31",
                location_id=loc_b01.id,
                status=STATUS_REGISTERED
            ),
        ]
        db.add_all(batches)
        db.flush()

        for loc in [loc_a01, loc_b01]:
            loc.used = db.query(models.Batch).filter(
                models.Batch.location_id == loc.id
            ).count()

        db.commit()

    db.close()


migrate_db()
init_sample_data()


@app.get("/api/health", summary="健康检查")
def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/users", response_model=schemas.UserResponse, summary="创建用户")
def create_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"用户名 {user_in.username} 已存在")
    if user_in.role not in [ROLE_OPERATOR, ROLE_REVIEWER]:
        raise HTTPException(status_code=400, detail=f"角色必须是 {ROLE_OPERATOR} 或 {ROLE_REVIEWER}")
    user = models.User(username=user_in.username, role=user_in.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/users", summary="用户列表")
def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return {"items": users, "total": len(users)}


@app.post("/api/locations", response_model=schemas.LocationResponse, summary="创建库位")
def create_location(loc_in: schemas.LocationCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Location).filter(models.Location.code == loc_in.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"库位编码 {loc_in.code} 已存在")
    location = models.Location(
        code=loc_in.code,
        name=loc_in.name,
        capacity=loc_in.capacity,
        used=0
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@app.get("/api/locations", summary="库位列表")
def list_locations(db: Session = Depends(get_db)):
    locations = db.query(models.Location).all()
    return {"items": locations, "total": len(locations)}


@app.get("/api/locations/{code}", response_model=schemas.LocationResponse, summary="库位详情")
def get_location(code: str, db: Session = Depends(get_db)):
    return get_location_or_404(db, code)


@app.post("/api/locations/{code}/freeze", response_model=schemas.LocationResponse, summary="冻结库位")
def freeze_location(code: str, req: schemas.LocationActionRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_REVIEWER])

    location = get_location_or_404(db, code)
    if location.frozen:
        raise HTTPException(
            status_code=400,
            detail=f"库位 {code} 已处于冻结状态"
        )

    location.frozen = True
    add_location_log(db, location.id, user.id, ACTION_LOCATION_FREEZE, remark=req.remark)
    db.commit()
    db.refresh(location)
    return location


@app.post("/api/locations/{code}/unfreeze", response_model=schemas.LocationResponse, summary="解冻库位")
def unfreeze_location(code: str, req: schemas.LocationActionRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_REVIEWER])

    location = get_location_or_404(db, code)
    if not location.frozen:
        raise HTTPException(
            status_code=400,
            detail=f"库位 {code} 未处于冻结状态"
        )

    location.frozen = False
    add_location_log(db, location.id, user.id, ACTION_LOCATION_UNFREEZE, remark=req.remark)
    db.commit()
    db.refresh(location)
    return location


@app.get("/api/location-logs", summary="库位操作日志查询")
def list_location_logs(
    location_code: Optional[str] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.LocationLog)

    if location_code:
        loc = db.query(models.Location).filter(models.Location.code == location_code).first()
        if loc:
            query = query.filter(models.LocationLog.location_id == loc.id)
        else:
            return {"items": [], "total": 0}

    if username:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            query = query.filter(models.LocationLog.user_id == user.id)
        else:
            return {"items": [], "total": 0}

    if action:
        query = query.filter(models.LocationLog.action == action)

    query = query.order_by(models.LocationLog.created_at.desc())
    logs = query.all()
    items = [location_log_to_response(log) for log in logs]
    return {"items": items, "total": len(items)}


@app.get("/api/export/location-logs", summary="导出库位操作日志为 JSON")
def export_location_logs(
    location_code: Optional[str] = None,
    username: Optional[str] = None,
    db: Session = Depends(get_db)
):
    result = list_location_logs(location_code=location_code, username=username, db=db)

    export_data = {
        "export_time": datetime.utcnow().isoformat(),
        "filter": {
            "location_code": location_code,
            "username": username
        },
        "total": result["total"],
        "records": []
    }

    for log in result["items"]:
        export_data["records"].append({
            "id": log.id,
            "location_code": log.location_code,
            "operator": log.username,
            "operator_role": log.user_role,
            "action": log.action,
            "remark": log.remark,
            "operated_at": log.created_at.isoformat()
        })

    return JSONResponse(
        content=export_data,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="location_logs_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json"'
        }
    )


@app.post("/api/batches", response_model=schemas.BatchResponse, summary="登记留样批次")
def create_batch(batch_in: schemas.BatchCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Batch).filter(models.Batch.batch_no == batch_in.batch_no).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"批次号 {batch_in.batch_no} 已存在")

    user = get_user_or_404(db, batch_in.username)

    location = get_location_or_404(db, batch_in.location_code)
    if location.used >= location.capacity:
        raise HTTPException(
            status_code=400,
            detail=f"库位 {location.code} 容量已满（{location.used}/{location.capacity}），无法存放新批次"
        )
    if location.frozen:
        raise HTTPException(
            status_code=400,
            detail=f"库位 {location.code} 已冻结，不能登记新批次"
        )

    batch = models.Batch(
        batch_no=batch_in.batch_no,
        reagent_name=batch_in.reagent_name,
        total_quantity=batch_in.total_quantity,
        available_quantity=batch_in.total_quantity,
        expiry_date=batch_in.expiry_date,
        location_id=location.id,
        status=STATUS_REGISTERED
    )
    db.add(batch)
    location.used += 1
    db.flush()

    add_audit_log(
        db, batch.id, user.id, ACTION_REGISTER,
        quantity=batch_in.total_quantity,
        from_status=None,
        to_status=STATUS_REGISTERED,
        remark=batch_in.remark
    )

    db.commit()
    db.refresh(batch)
    return batch_to_response(batch)


@app.get("/api/batches", summary="批次列表")
def list_batches(
    status: Optional[str] = None,
    location_code: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Batch)
    if status:
        query = query.filter(models.Batch.status == status)
    if location_code:
        loc = db.query(models.Location).filter(models.Location.code == location_code).first()
        if loc:
            query = query.filter(models.Batch.location_id == loc.id)
    batches = query.all()
    items = [batch_to_response(b) for b in batches]
    return {"items": items, "total": len(items)}


@app.get("/api/batches/{batch_no}", response_model=schemas.BatchResponse, summary="批次详情")
def get_batch(batch_no: str, db: Session = Depends(get_db)):
    batch = get_batch_or_404(db, batch_no)
    return batch_to_response(batch)


@app.post("/api/batches/{batch_no}/pickup", response_model=schemas.BatchResponse, summary="领取留样")
def pickup_sample(batch_no: str, req: schemas.ActionRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_OPERATOR, ROLE_REVIEWER])

    batch = get_batch_or_404(db, batch_no)

    if batch.status not in [STATUS_REGISTERED, STATUS_IN_USE]:
        raise HTTPException(
            status_code=400,
            detail=f"批次 {batch_no} 当前状态为 {batch.status}，不能领取"
        )

    if req.quantity is None:
        raise HTTPException(status_code=400, detail="领取数量不能为空")

    if req.quantity > batch.available_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"领取数量 {req.quantity} 超过可用库存 {batch.available_quantity}"
        )

    from_status = batch.status
    batch.available_quantity -= req.quantity
    batch.status = STATUS_IN_USE
    to_status = STATUS_IN_USE

    add_audit_log(
        db, batch.id, user.id, ACTION_PICKUP,
        quantity=req.quantity,
        from_status=from_status,
        to_status=to_status,
        remark=req.remark
    )

    db.commit()
    db.refresh(batch)
    return batch_to_response(batch)


@app.post("/api/batches/{batch_no}/return", response_model=schemas.BatchResponse, summary="归还留样")
def return_sample(batch_no: str, req: schemas.ActionRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_OPERATOR, ROLE_REVIEWER])

    batch = get_batch_or_404(db, batch_no)

    if batch.status not in [STATUS_IN_USE, STATUS_PENDING_REVIEW]:
        raise HTTPException(
            status_code=400,
            detail=f"批次 {batch_no} 当前状态为 {batch.status}，不能归还"
        )

    if req.quantity is None:
        raise HTTPException(status_code=400, detail="归还数量不能为空")

    returned_total = batch.total_quantity - batch.available_quantity
    if req.quantity > returned_total:
        raise HTTPException(
            status_code=400,
            detail=f"归还数量 {req.quantity} 超过已领用量 {returned_total}"
        )

    from_status = batch.status
    batch.available_quantity += req.quantity
    batch.status = STATUS_PENDING_REVIEW
    to_status = STATUS_PENDING_REVIEW

    add_audit_log(
        db, batch.id, user.id, ACTION_RETURN,
        quantity=req.quantity,
        from_status=from_status,
        to_status=to_status,
        remark=req.remark
    )

    db.commit()
    db.refresh(batch)
    return batch_to_response(batch)


@app.post("/api/batches/{batch_no}/seal", response_model=schemas.BatchResponse, summary="复核封存")
def seal_sample(batch_no: str, req: schemas.ActionRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_REVIEWER])

    batch = get_batch_or_404(db, batch_no)

    if batch.status != STATUS_PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"批次 {batch_no} 当前状态为 {batch.status}，只有待复核状态才能封存"
        )

    from_status = batch.status
    batch.status = STATUS_SEALED
    to_status = STATUS_SEALED

    add_audit_log(
        db, batch.id, user.id, ACTION_SEAL,
        from_status=from_status,
        to_status=to_status,
        remark=req.remark
    )

    db.commit()
    db.refresh(batch)
    return batch_to_response(batch)


@app.post("/api/batches/{batch_no}/scrap", response_model=schemas.BatchResponse, summary="报废")
def scrap_sample(batch_no: str, req: schemas.ActionRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_REVIEWER])

    batch = get_batch_or_404(db, batch_no)

    if batch.status in [STATUS_SEALED, STATUS_SCRAPPED]:
        raise HTTPException(
            status_code=400,
            detail=f"批次 {batch_no} 当前状态为 {batch.status}，不能报废"
        )

    from_status = batch.status
    batch.status = STATUS_SCRAPPED
    to_status = STATUS_SCRAPPED

    add_audit_log(
        db, batch.id, user.id, ACTION_SCRAP,
        from_status=from_status,
        to_status=to_status,
        remark=req.remark
    )

    db.commit()
    db.refresh(batch)
    return batch_to_response(batch)


@app.get("/api/audit-logs", summary="审计日志查询")
def list_audit_logs(
    batch_no: Optional[str] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.AuditLog)

    if batch_no:
        batch = db.query(models.Batch).filter(models.Batch.batch_no == batch_no).first()
        if batch:
            query = query.filter(models.AuditLog.batch_id == batch.id)
        else:
            return {"items": [], "total": 0}

    if username:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            query = query.filter(models.AuditLog.user_id == user.id)
        else:
            return {"items": [], "total": 0}

    if action:
        query = query.filter(models.AuditLog.action == action)

    query = query.order_by(models.AuditLog.created_at.desc())
    logs = query.all()
    items = [audit_log_to_response(log) for log in logs]
    return {"items": items, "total": len(items)}


@app.get("/api/export/audit", summary="导出审计日志为 JSON")
def export_audit_logs(
    batch_no: Optional[str] = None,
    username: Optional[str] = None,
    db: Session = Depends(get_db)
):
    result = list_audit_logs(batch_no=batch_no, username=username, db=db)

    export_data = {
        "export_time": datetime.utcnow().isoformat(),
        "filter": {
            "batch_no": batch_no,
            "username": username
        },
        "total": result["total"],
        "records": []
    }

    for log in result["items"]:
        export_data["records"].append({
            "id": log.id,
            "batch_no": log.batch_no,
            "operator": log.username,
            "operator_role": log.user_role,
            "action": log.action,
            "quantity": log.quantity,
            "from_status": log.from_status,
            "to_status": log.to_status,
            "remark": log.remark,
            "operated_at": log.created_at.isoformat()
        })

    return JSONResponse(
        content=export_data,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="audit_log_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json"'
        }
    )


@app.post("/api/batches/{batch_no}/transfer", response_model=schemas.BatchTransferResponse, summary="调拨批次到新库位")
def transfer_batch(batch_no: str, req: schemas.BatchTransferCreate, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_REVIEWER])

    batch = get_batch_or_404(db, batch_no)

    if batch.status in [STATUS_SEALED, STATUS_SCRAPPED]:
        raise HTTPException(
            status_code=400,
            detail=f"批次 {batch_no} 当前状态为 {batch.status}，已封存或已报废，不能调拨"
        )

    to_location = get_location_or_404(db, req.to_location_code)
    from_location = batch.location

    if from_location.id == to_location.id:
        raise HTTPException(
            status_code=400,
            detail=f"源库位和目标库位相同（{from_location.code}），无需调拨"
        )

    if to_location.frozen:
        raise HTTPException(
            status_code=400,
            detail=f"目标库位 {to_location.code} 已冻结，不能调入"
        )

    if to_location.used >= to_location.capacity:
        raise HTTPException(
            status_code=400,
            detail=f"目标库位 {to_location.code} 容量已满（{to_location.used}/{to_location.capacity}），无法调入"
        )

    transfer = models.BatchTransfer(
        batch_id=batch.id,
        from_location_id=from_location.id,
        to_location_id=to_location.id,
        user_id=user.id,
        remark=req.remark
    )
    db.add(transfer)

    batch.location_id = to_location.id
    from_location.used -= 1
    to_location.used += 1
    db.flush()

    add_audit_log(
        db, batch.id, user.id, ACTION_TRANSFER,
        from_status=batch.status,
        to_status=batch.status,
        remark=f"从 {from_location.code} 调拨到 {to_location.code}" + (f"，{req.remark}" if req.remark else "")
    )

    add_location_log(
        db, from_location.id, user.id, ACTION_LOCATION_TRANSFER_OUT,
        remark=f"调出批次 {batch_no} 到 {to_location.code}" + (f"，{req.remark}" if req.remark else "")
    )
    add_location_log(
        db, to_location.id, user.id, ACTION_LOCATION_TRANSFER_IN,
        remark=f"从 {from_location.code} 调入批次 {batch_no}" + (f"，{req.remark}" if req.remark else "")
    )

    db.commit()
    db.refresh(transfer)
    return transfer_to_response(transfer)


@app.get("/api/transfers", summary="调拨记录查询")
def list_transfers(
    batch_no: Optional[str] = None,
    from_location_code: Optional[str] = None,
    to_location_code: Optional[str] = None,
    username: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.BatchTransfer)

    if batch_no:
        batch = db.query(models.Batch).filter(models.Batch.batch_no == batch_no).first()
        if batch:
            query = query.filter(models.BatchTransfer.batch_id == batch.id)
        else:
            return {"items": [], "total": 0}

    if from_location_code:
        loc = db.query(models.Location).filter(models.Location.code == from_location_code).first()
        if loc:
            query = query.filter(models.BatchTransfer.from_location_id == loc.id)
        else:
            return {"items": [], "total": 0}

    if to_location_code:
        loc = db.query(models.Location).filter(models.Location.code == to_location_code).first()
        if loc:
            query = query.filter(models.BatchTransfer.to_location_id == loc.id)
        else:
            return {"items": [], "total": 0}

    if username:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            query = query.filter(models.BatchTransfer.user_id == user.id)
        else:
            return {"items": [], "total": 0}

    query = query.order_by(models.BatchTransfer.created_at.desc())
    transfers = query.all()
    items = [transfer_to_response(t) for t in transfers]
    return {"items": items, "total": len(items)}


@app.get("/api/export/transfers", summary="导出调拨记录为 JSON")
def export_transfers(
    batch_no: Optional[str] = None,
    from_location_code: Optional[str] = None,
    to_location_code: Optional[str] = None,
    username: Optional[str] = None,
    db: Session = Depends(get_db)
):
    result = list_transfers(
        batch_no=batch_no,
        from_location_code=from_location_code,
        to_location_code=to_location_code,
        username=username,
        db=db
    )

    export_data = {
        "export_time": datetime.utcnow().isoformat(),
        "filter": {
            "batch_no": batch_no,
            "from_location_code": from_location_code,
            "to_location_code": to_location_code,
            "username": username
        },
        "total": result["total"],
        "records": []
    }

    for t in result["items"]:
        export_data["records"].append({
            "id": t.id,
            "batch_no": t.batch_no,
            "from_location_code": t.from_location_code,
            "to_location_code": t.to_location_code,
            "operator": t.username,
            "operator_role": t.user_role,
            "remark": t.remark,
            "operated_at": t.created_at.isoformat()
        })

    return JSONResponse(
        content=export_data,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="transfers_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json"'
        }
    )


@app.post("/api/locations/{code}/temp-config", response_model=schemas.LocationResponse, summary="配置库位温控监控")
def configure_temp_monitoring(code: str, req: schemas.LocationTempConfigRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_REVIEWER])

    location = get_location_or_404(db, code)

    if req.monitoring_enabled:
        if req.temp_min is None or req.temp_max is None:
            raise HTTPException(
                status_code=400,
                detail="启用监控时必须设置最低温度和最高温度"
            )
        if req.temp_min >= req.temp_max:
            raise HTTPException(
                status_code=400,
                detail="最低温度必须小于最高温度"
            )

    location.monitoring_enabled = req.monitoring_enabled
    location.temp_min = req.temp_min if req.monitoring_enabled else None
    location.temp_max = req.temp_max if req.monitoring_enabled else None

    config_desc = f"启用监控({req.temp_min}~{req.temp_max}°C)" if req.monitoring_enabled else "关闭监控"
    add_location_log(
        db, location.id, user.id, ACTION_TEMP_CONFIG,
        remark=config_desc
    )

    db.commit()
    db.refresh(location)
    return location


@app.post("/api/locations/{code}/temperature-inspections", response_model=schemas.TemperatureInspectionResponse, summary="提交温控巡检记录")
def submit_temperature_inspection(code: str, req: schemas.TemperatureInspectionCreate, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_OPERATOR, ROLE_REVIEWER])

    location = get_location_or_404(db, code)

    if not location.monitoring_enabled:
        raise HTTPException(
            status_code=400,
            detail=f"库位 {code} 未启用温控监控，不能提交巡检记录"
        )

    try:
        insp_date = date.fromisoformat(req.inspection_date)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="巡检日期格式无效，需为 YYYY-MM-DD"
        )

    existing = db.query(models.TemperatureInspection).filter(
        models.TemperatureInspection.location_id == location.id,
        models.TemperatureInspection.inspection_date == insp_date,
        models.TemperatureInspection.user_id == user.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"用户 {req.username} 已在 {req.inspection_date} 对库位 {code} 提交过巡检记录"
        )

    inspection = models.TemperatureInspection(
        location_id=location.id,
        user_id=user.id,
        temperature=req.temperature,
        inspection_date=insp_date,
        remark=req.remark
    )
    db.add(inspection)
    db.flush()

    add_location_log(
        db, location.id, user.id, ACTION_TEMP_INSPECT,
        remark=f"温度: {req.temperature}°C"
    )

    alert = None
    if (location.temp_min is not None and req.temperature < location.temp_min) or \
       (location.temp_max is not None and req.temperature > location.temp_max):
        alert = models.TemperatureAlert(
            location_id=location.id,
            inspection_id=inspection.id,
            temperature=req.temperature,
            temp_min=location.temp_min,
            temp_max=location.temp_max,
            status="OPEN"
        )
        db.add(alert)
        db.flush()

        add_location_log(
            db, location.id, user.id, ACTION_TEMP_ALERT,
            remark=f"温度异常: {req.temperature}°C，范围 {location.temp_min}~{location.temp_max}°C"
        )

    db.commit()
    db.refresh(inspection)
    return inspection_to_response(inspection)


@app.get("/api/locations/{code}/temperature-inspections", summary="查询库位巡检记录")
def list_temperature_inspections(
    code: str,
    inspection_date: Optional[str] = None,
    username: Optional[str] = None,
    db: Session = Depends(get_db)
):
    location = get_location_or_404(db, code)

    query = db.query(models.TemperatureInspection).filter(
        models.TemperatureInspection.location_id == location.id
    )

    if inspection_date:
        try:
            insp_date = date.fromisoformat(inspection_date)
            query = query.filter(models.TemperatureInspection.inspection_date == insp_date)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="日期格式无效，需为 YYYY-MM-DD")

    if username:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            query = query.filter(models.TemperatureInspection.user_id == user.id)
        else:
            return {"items": [], "total": 0}

    query = query.order_by(models.TemperatureInspection.created_at.desc())
    inspections = query.all()
    items = [inspection_to_response(insp) for insp in inspections]
    return {"items": items, "total": len(items)}


@app.get("/api/temperature-inspections", summary="查询所有巡检记录（operator 只看自己的）")
def list_all_temperature_inspections(
    location_code: Optional[str] = None,
    inspection_date: Optional[str] = None,
    username: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.TemperatureInspection)

    if location_code:
        loc = db.query(models.Location).filter(models.Location.code == location_code).first()
        if loc:
            query = query.filter(models.TemperatureInspection.location_id == loc.id)
        else:
            return {"items": [], "total": 0}

    if inspection_date:
        try:
            insp_date = date.fromisoformat(inspection_date)
            query = query.filter(models.TemperatureInspection.inspection_date == insp_date)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="日期格式无效，需为 YYYY-MM-DD")

    if username:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            query = query.filter(models.TemperatureInspection.user_id == user.id)
        else:
            return {"items": [], "total": 0}

    query = query.order_by(models.TemperatureInspection.created_at.desc())
    inspections = query.all()
    items = [inspection_to_response(insp) for insp in inspections]
    return {"items": items, "total": len(items)}


@app.get("/api/temperature-alerts", summary="查询温控异常单")
def list_temperature_alerts(
    location_code: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.TemperatureAlert)

    if location_code:
        loc = db.query(models.Location).filter(models.Location.code == location_code).first()
        if loc:
            query = query.filter(models.TemperatureAlert.location_id == loc.id)
        else:
            return {"items": [], "total": 0}

    if status:
        query = query.filter(models.TemperatureAlert.status == status)

    query = query.order_by(models.TemperatureAlert.created_at.desc())
    alerts = query.all()
    items = [alert_to_response(a) for a in alerts]
    return {"items": items, "total": len(items)}


@app.post("/api/temperature-alerts/{alert_id}/handle", response_model=schemas.TemperatureAlertResponse, summary="处理温控异常单")
def handle_temperature_alert(alert_id: int, req: schemas.TemperatureAlertHandleRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, req.username)
    require_role(user, [ROLE_REVIEWER])

    alert = db.query(models.TemperatureAlert).filter(models.TemperatureAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"异常单 {alert_id} 不存在")

    if alert.status != "OPEN":
        raise HTTPException(
            status_code=400,
            detail=f"异常单 {alert_id} 当前状态为 {alert.status}，只能处理 OPEN 状态的异常单"
        )

    alert.status = "HANDLED"
    alert.handler_id = user.id
    alert.reason = req.reason
    alert.disposal = req.disposal
    alert.handled_at = datetime.utcnow()

    add_location_log(
        db, alert.location_id, user.id, ACTION_TEMP_ALERT_HANDLE,
        remark=f"处理异常单 #{alert_id}，原因: {req.reason}，处置: {req.disposal}"
    )

    db.commit()
    db.refresh(alert)
    return alert_to_response(alert)


@app.get("/api/export/temperature", summary="导出巡检和异常记录为 JSON")
def export_temperature(
    location_code: Optional[str] = None,
    inspection_date: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    insp_result = list_all_temperature_inspections(
        location_code=location_code,
        inspection_date=inspection_date,
        db=db
    )

    alert_result = list_temperature_alerts(
        location_code=location_code,
        status=status,
        db=db
    )

    export_data = {
        "export_time": datetime.utcnow().isoformat(),
        "filter": {
            "location_code": location_code,
            "inspection_date": inspection_date,
            "alert_status": status
        },
        "inspections": {
            "total": insp_result["total"],
            "records": []
        },
        "alerts": {
            "total": alert_result["total"],
            "records": []
        }
    }

    for insp in insp_result["items"]:
        export_data["inspections"]["records"].append({
            "id": insp.id,
            "location_code": insp.location_code,
            "operator": insp.username,
            "operator_role": insp.user_role,
            "temperature": insp.temperature,
            "inspection_date": insp.inspection_date,
            "remark": insp.remark,
            "created_at": insp.created_at.isoformat()
        })

    for a in alert_result["items"]:
        export_data["alerts"]["records"].append({
            "id": a.id,
            "location_code": a.location_code,
            "temperature": a.temperature,
            "temp_min": a.temp_min,
            "temp_max": a.temp_max,
            "status": a.status,
            "handler": a.handler_name,
            "reason": a.reason,
            "disposal": a.disposal,
            "handled_at": a.handled_at.isoformat() if a.handled_at else None,
            "created_at": a.created_at.isoformat()
        })

    return JSONResponse(
        content=export_data,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="temperature_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json"'
        }
    )
