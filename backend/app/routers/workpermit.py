"""作业票接口：维护作业票，覆盖申请、签发施工许可、开工、完工、关闭等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.workpermit import WorkpermitService

router = APIRouter(prefix="/api/workpermit", tags=["作业票"])

service = WorkpermitService()

LIST_FIELDS = ["作业票编号", "作业名称", "风险等级", "作业区域", "监护人员", "作业内容", "计划开工日期", "作业状态"]
STATUSES = ["待签发", "已签发", "施工中", "已完工", "已关闭"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按作业票编号或作业名称检索"),
    status: str | None = Query(default=None, description="待签发、已签发、施工中、已完工、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号/名称与状态过滤作业票列表；历史已关闭票据同样返回，不会被删除。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出作业票清单：返回当前过滤条件下的全量数据（含历史已关闭票据）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "workpermit", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条作业票详情；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"作业票 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条作业票申请，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="作业票已提交申请，等待签发施工许可", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条作业票执行签发施工许可、开工、完工、关闭；跳级/倒序/重复会被拦下并说明当前状态。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
