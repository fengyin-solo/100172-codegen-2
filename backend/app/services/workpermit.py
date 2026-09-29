"""作业票业务规则：申请、签发施工许可、开工、完工、关闭的状态流转与并发控制。

完整状态序列（只能逐级前进，跳级或倒序都会被拦下并说明当前状态）：

    待签发 ──签发施工许可──▶ 已签发 ──开工──▶ 施工中 ──完工──▶ 已完工 ──关闭──▶ 已关闭

同一张票并发提交两份「签发施工许可」时，用互斥锁把「读取当前状态 → 校验 → 写入」
作为一个临界区串行化：只有第一个请求能把状态从「待签发」改成「已签发」，第二个请求
读到的已是「已签发」，签发不再是当前状态的下一步，因而被拦下，保证许可只生效一次。
"""
from __future__ import annotations

import threading
from typing import Any

from app.store import store

MODULE = "workpermit"
REQUIRED_FIELDS = ["作业票编号", "作业名称", "风险等级", "作业区域", "监护人员"]

# 状态序列：下标即流转次序，动作只能把状态推进到下标 +1 的位置。
STATUS_ORDER = ["待签发", "已签发", "施工中", "已完工", "已关闭"]
# 动作 → 目标状态。
ACTION_RULES = {
    "签发施工许可": "已签发",
    "开工": "施工中",
    "完工": "已完工",
    "关闭": "已关闭",
}
TERMINAL_STATUS = STATUS_ORDER[-1]

# 串行化同一张票的状态变更（内存仓库下用进程内锁即可；换数据库时对应行锁/乐观锁）。
_action_lock = threading.Lock()


def _action_to(target: str) -> str | None:
    """找到能把状态推进到 target 的动作名，用于错误提示。"""
    for action, status in ACTION_RULES.items():
        if status == target:
            return action
    return None


class WorkpermitService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("作业票编号", ""))
                or keyword in str(row.get("作业名称", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """登记一条作业票申请；风险等级、作业区域、监护人员为必填。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ["作业票编号", "作业名称", "风险等级", "作业区域", "监护人员", "作业内容", "计划开工日期"]:
            entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["作业状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = str(values.get("风险等级") or "").strip() == "高风险"
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        with _action_lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"作业票 {entry_id} 不存在或已归档"
            if action not in ACTION_RULES:
                return None, f"动作「{action}」不属于作业票可执行范围"

            current = str(entry.get("status") or "")
            target = ACTION_RULES[action]
            cur_idx = STATUS_ORDER.index(current) if current in STATUS_ORDER else -1
            tgt_idx = STATUS_ORDER.index(target)
            ticket_no = str(entry.get("作业票编号") or entry_id)
            flow = " → ".join(STATUS_ORDER)

            if tgt_idx != cur_idx + 1:
                # 目标不是当前状态的下一步：倒序 / 重复提交（含并发重复签发）/ 跳级。
                if tgt_idx <= cur_idx:
                    return None, (
                        f"作业票「{ticket_no}」当前状态为「{current}」，"
                        f"「{action}」是已经走过的环节，不能重复生效或倒序执行；"
                        f"状态只能按 {flow} 的顺序流转。"
                    )
                return None, (
                    f"作业票「{ticket_no}」当前状态为「{current}」，"
                    f"不能跳过前置环节直接「{action}」；请先完成上一步"
                    f"「{_action_to(STATUS_ORDER[cur_idx + 1])}」。"
                )

            entry["status"] = target
            entry["作业状态"] = target
            # 关闭后即为历史票据：不再计入待处理，但保留记录可供查询。
            entry["pending"] = target != TERMINAL_STATUS
            return entry, f"作业票已{action}"
