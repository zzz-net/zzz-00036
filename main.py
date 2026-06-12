from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
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


@app.on_event("startup")
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

        for loc in [loc_a01, loc_b01]:
            loc.used = db.query(models.Batch).filter(
                models.Batch.location_id == loc.id
            ).count()

        db.commit()

    db.close()


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


@app.post("/api/batches", response_model=schemas.BatchResponse, summary="登记留样批次")
def create_batch(batch_in: schemas.BatchCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Batch).filter(models.Batch.batch_no == batch_in.batch_no).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"批次号 {batch_in.batch_no} 已存在")

    location = get_location_or_404(db, batch_in.location_code)
    if location.used >= location.capacity:
        raise HTTPException(
            status_code=400,
            detail=f"库位 {location.code} 容量已满（{location.used}/{location.capacity}），无法存放新批次"
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
