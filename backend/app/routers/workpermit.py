"""作业票接口：覆盖申请、施工许可签发、开工、完工、关闭的完整状态流转。

状态校验全部在服务层完成；路由层只负责参数接收与结果包装。/board、/export
这类固定路径要排在 /{entry_id} 之前，避免被动态路径抢先匹配。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.workpermit import WorkPermitService

router = APIRouter(prefix="/api/workpermit", tags=["作业票管理"])

service = WorkPermitService()

LIST_FIELDS = [
    "作业票编号", "作业内容", "风险等级", "作业区域", "监护人员",
    "申请人员", "许可签发人员", "申请时间", "实际开工时间", "实际完工时间",
]
ACTIONS = ["签发许可", "开工", "确认完工", "关闭票据"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按作业票编号、作业内容检索"),
    status: str | None = Query(default=None, description="待签发、已签发、施工中、已完工、已关闭"),
    risk_level: str | None = Query(default=None, alias="riskLevel", description="重大/较大/一般/低风险"),
    area: str | None = Query(default=None, description="按作业区域模糊检索"),
    include_closed: bool = Query(default=True, alias="includeClosed", description="是否包含已关闭的历史票"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号、状态、风险等级、区域过滤作业票；历史已关闭的票默认保留可查。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        risk_level=risk_level,
        area=area,
        include_closed=include_closed,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/board")
def board() -> dict[str, Any]:
    """作业票看板：在施工作业数、各状态票据数与在施明细，供状态变更后同步刷新。"""
    return service.board()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出作业票全量清单（含已关闭的历史票）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "workpermit", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单张作业票详情与流转轨迹；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"作业票 {entry_id} 不存在")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """申请一张作业票，登记作业内容、区域、风险等级与监护人员。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少或不合规的字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="作业票申请已提交，等待签发施工许可", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """执行签发许可、开工、确认完工、关闭票据；跳级、倒序或重复签发都会被拦下。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "").strip() or None
    entry, message = service.run_action(entry_id, action, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
