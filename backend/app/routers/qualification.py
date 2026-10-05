"""人员资质档案接口：备案登记、复训结论、队组名册与待办；跨队组只读，越权当场打回。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.qualification import QualificationService

router = APIRouter(prefix="/api/qualification", tags=["人员资质"])

service = QualificationService()


@router.get("/meta")
def meta() -> dict[str, Any]:
    """队组清单、证书类别与复训结论选项，前端据此渲染下拉框。"""
    return service.meta()


@router.get("/roster")
def team_roster(team: str = Query(..., description="队组名称")) -> dict[str, Any]:
    """上岗名册：按最近一次备案归并，复训未通过的不在册。"""
    items = service.team_roster(team)
    return {"team": team, "total": len(items), "items": items}


@router.get("/todos")
def team_todos(team: str = Query(..., description="队组名称")) -> dict[str, Any]:
    """队组待办列表：复训结论会实时写入这里。"""
    items = service.team_todos(team)
    return {"team": team, "total": len(items), "items": items}


@router.post("/roster/validate", response_model=ActionResult)
def validate_candidate(payload: EntryPayload) -> ActionResult:
    """工作票选人校验：名册之外的人不许被工作票选中。"""
    team = str(payload.values.get("队组") or "").strip()
    name = str(payload.values.get("姓名") or "").strip()
    ok, message = service.validate_candidate(team, name)
    return ActionResult(ok=ok, message=message)


@router.get("", response_model=PageResult[dict])
def list_archives(
    keyword: str | None = Query(default=None, description="按姓名或档案编号检索"),
    team: str | None = Query(default=None, description="按所属队组过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """档案列表：跨队组也可查看，查看不受队组归属限制。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_archives(keyword=keyword, team=team, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出人员资质档案清单：返回当前全量数据。"""
    items, total = service.list_archives(page=1, size=10000)
    return {"module": "qualification", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_archive(entry_id: int) -> dict:
    """读取单条资质档案明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"资质档案 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_archive(payload: EntryPayload) -> ActionResult:
    """登记一条人员资质档案；越权提交当场打回并写清缺哪一项授权。"""
    operator_team = str(payload.values.get("操作队组") or "").strip()
    entry, missing, denial = service.create_entry(payload.values, operator_team)
    if denial:
        raise HTTPException(status_code=403, detail=denial)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="人员资质档案已备案", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """录入复训结论（复训通过、复训未通过）；未通过者自动从本队组名册摘除。"""
    action = str(payload.values.get("action") or "").strip()
    operator_team = str(payload.values.get("操作队组") or "").strip()
    entry, message, denial = service.record_retraining(entry_id, action, operator_team)
    if denial:
        raise HTTPException(status_code=403, detail=denial)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
