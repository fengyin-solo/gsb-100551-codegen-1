"""人员资质档案接口：档案查询、备案登记、复训结论、上岗名册、队组待办与工作票选人校验。

跨队组只读：所有读接口不限队组；写操作按提交人当前队组判定归属（请求体
operator_team 字段，或请求头 X-Operator-Team；中文队组名请走请求体，HTTP 头
只保证 latin-1 编码），越权提交当场打回（403），并在报文里写清缺哪一项授权。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.qualification import PermissionDenied, QualificationService

router = APIRouter(prefix="/api/qualification", tags=["人员资质档案"])

service = QualificationService()


@router.get("", response_model=PageResult[dict])
def list_archive(
    keyword: str | None = Query(default=None, description="按姓名或工号检索"),
    team: str | None = Query(default=None, description="按所属队组过滤（最近一次备案）"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """资质档案列表：所属队组按最近一次备案算；任何队组都可读。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_archive(keyword=keyword, team=team, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/teams")
def list_teams() -> dict[str, Any]:
    """队组清单：给队组切换器和权限判定用。"""
    return {"items": service.db.list_teams()}


@router.get("/summary")
def summary() -> dict[str, Any]:
    """看板卡片：档案人数、临期证书、已过期证书、待处理待办。"""
    return {"cards": service.summary()}


@router.get("/roster")
def list_roster(team: str = Query(description="队组名称")) -> dict[str, Any]:
    """指定队组的上岗名册；名册之外的人不许被工作票选中。"""
    if not service.db.team_exists(team):
        raise HTTPException(status_code=404, detail=f"队组「{team}」不存在")
    return {"team": team, "items": service.list_roster(team)}


@router.get("/todos")
def list_todos(team: str = Query(description="队组名称")) -> dict[str, Any]:
    """指定队组的待办列表：复训结论都会写在这里。"""
    if not service.db.team_exists(team):
        raise HTTPException(status_code=404, detail=f"队组「{team}」不存在")
    return {"team": team, "items": service.list_todos(team)}


@router.get("/{person_id}", response_model=dict)
def get_person(person_id: int) -> dict:
    """单人档案明细：含全部备案记录与证书；任何队组都可读。"""
    entry = service.get_person(person_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"人员档案 {person_id} 不存在")
    return entry


@router.post("/filings", response_model=ActionResult)
def create_filing(
    payload: EntryPayload,
    x_operator_team: str | None = Header(default=None),
) -> ActionResult:
    """登记备案：老记录不填备案日期时按入场日期回填，过往证书沿用原有有效期。"""
    operator_team = payload.operator_team or x_operator_team
    try:
        entry, error = service.create_filing(payload.values, operator_team=operator_team)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if error:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="备案已登记，名册已同步", entry=entry)


@router.post("/retraining", response_model=ActionResult)
def record_retraining(
    payload: EntryPayload,
    x_operator_team: str | None = Header(default=None),
) -> ActionResult:
    """录入复训结论：未过关自动移出本队组名册，结论同事务写入队组待办。"""
    operator_team = payload.operator_team or x_operator_team
    try:
        entry, message = service.record_retraining(payload.values, operator_team=operator_team)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/work-ticket/check", response_model=ActionResult)
def work_ticket_check(payload: EntryPayload) -> ActionResult:
    """工作票选人校验：名册之外的人不许被工作票选中。校验本身是读取，不限队组。"""
    ok, message = service.work_ticket_check(payload.values)
    return ActionResult(ok=ok, message=message)
