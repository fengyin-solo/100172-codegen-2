"""作业票业务规则：申请、签发、开工、完工、关闭五段状态严格顺序流转。

和其它模块不同，这里的状态机有两条硬约束：
1. 只能顺着状态序列一步一步走，跳级（例如「待签发」直接「确认完工」）和
   倒序（例如「已关闭」再「开工」）都会被拦下，并在提示里说明当前状态；
2. 「签发许可」用进程锁做临界区，同一张票并发提交两份许可时，只有第一份
   能把状态从「待签发」改成「已签发」，第二份读到的已是新状态，按重复提交驳回。

每次动作都会追加一条流转记录，票据详情据此展示完整轨迹；已关闭的票不做删除，
仍然保留在列表里可查。
"""
from __future__ import annotations

import threading
from datetime import date
from typing import Any

from app.store import store

MODULE = "workpermit"
REQUIRED_FIELDS = ["作业内容", "作业区域", "风险等级", "监护人员"]
RISK_LEVELS = ["重大风险", "较大风险", "一般风险", "低风险"]

STATUS_ORDER = ["待签发", "已签发", "施工中", "已完工", "已关闭"]
# 每个动作的源状态：只有处于该状态的票才能执行，天然杜绝跳级与倒序。
ACTION_RULES: dict[str, dict[str, str]] = {
    "签发许可": {"from": "待签发", "to": "已签发"},
    "开工": {"from": "已签发", "to": "施工中"},
    "确认完工": {"from": "施工中", "to": "已完工"},
    "关闭票据": {"from": "已完工", "to": "已关闭"},
}
ACTION_TIME_FIELDS = {
    "签发许可": "许可签发时间",
    "开工": "实际开工时间",
    "确认完工": "实际完工时间",
    "关闭票据": "关闭时间",
}
# 在施工作业数看板口径。
ACTIVE_STATUS = "施工中"

# 串行化所有状态变更，保证「读当前状态 -> 判断 -> 落新状态」是原子的。
_transition_lock = threading.Lock()


def _today() -> str:
    return date.today().isoformat()


def _append_flow(
    entry: dict[str, Any],
    action: str,
    from_status: str | None,
    target: str,
    operator: str,
) -> None:
    """给票据追加一条流转记录；历史数据没有该字段时就地补一个空列表。"""
    history = entry.setdefault("flow_history", [])
    history.append({
        "seq": len(history) + 1,
        "action": action,
        "from_status": from_status,
        "to_status": target,
        "operator": operator or "值班管理员",
        "time": _today(),
    })


class WorkPermitService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        risk_level: str | None = None,
        area: str | None = None,
        include_closed: bool = True,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("作业票编号", ""))
                or keyword in str(row.get("作业内容", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if risk_level:
            rows = [row for row in rows if row.get("风险等级") == risk_level]
        if area:
            rows = [row for row in rows if area in str(row.get("作业区域", ""))]
        if not include_closed:
            rows = [row for row in rows if row.get("status") != "已关闭"]
        # 新票在前，方便先处理待签发、在施工的票。
        rows.sort(key=lambda row: int(row.get("id", 0)), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        risk_level = str(values.get("风险等级") or "").strip()
        if risk_level not in RISK_LEVELS:
            return None, [f"风险等级（需为：{'、'.join(RISK_LEVELS)}）"]
        rows = store.rows(MODULE)
        next_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        entry: dict[str, Any] = {
            "id": next_id,
            "作业票编号": f"WP-{date.today():%Y%m%d}-{next_id:04d}",
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": risk_level in ("重大风险", "较大风险"),
            "申请时间": _today(),
            "许可签发时间": None,
            "实际开工时间": None,
            "实际完工时间": None,
            "关闭时间": None,
            "flow_history": [],
        }
        for field in ("作业内容", "作业区域", "风险等级", "监护人员",
                      "申请人员", "许可签发人员", "作业单位"):
            entry[field] = str(values.get(field) or "").strip() or None
        rows.append(entry)
        _append_flow(entry, "提交申请", None, STATUS_ORDER[0], entry["申请人员"] or "申请人")
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于作业票可执行范围"
        rule = ACTION_RULES[action]
        expected = rule["from"]
        target = rule["to"]

        with _transition_lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"作业票 {entry_id} 不存在"
            current = str(entry.get("status") or "")

            if current == target:
                # 并发或重复点击会落到这里：许可只可能生效一次。
                if action == "签发许可":
                    return None, (
                        f"作业票 {entry_id} 的施工许可已签发生效，请勿重复提交许可"
                    )
                return None, f"作业票 {entry_id} 当前为「{current}」，动作「{action}」已执行过"

            if current != expected:
                try:
                    current_index = STATUS_ORDER.index(current)
                    expected_index = STATUS_ORDER.index(expected)
                except ValueError:
                    return None, f"作业票 {entry_id} 当前状态「{current}」无法识别"
                if current_index > expected_index:
                    reason = "状态不能倒序变更"
                else:
                    reason = "不能跳过中间状态"
                return None, (
                    f"{reason}：作业票 {entry_id} 当前为「{current}」，"
                    f"需先处于「{expected}」才能执行「{action}」"
                )

            entry["status"] = target
            entry[ACTION_TIME_FIELDS[action]] = _today()
            if action == "签发许可" and operator:
                entry["许可签发人员"] = operator
            entry["pending"] = target != STATUS_ORDER[-1]
            _append_flow(
                entry, action, current, target,
                operator or entry.get("许可签发人员") or "值班管理员",
            )
        return entry, f"作业票已{action}，当前状态：{target}"

    def board(self) -> dict[str, Any]:
        """看板：各状态票据数量，外加在施工作业数与高风险在施数。"""
        rows = store.rows(MODULE)
        status_counts = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = row.get("status")
            if status in status_counts:
                status_counts[status] += 1
        active_rows = [row for row in rows if row.get("status") == ACTIVE_STATUS]
        return {
            "total": len(rows),
            "active_count": len(active_rows),
            "high_risk_active": sum(
                1 for row in active_rows if row.get("风险等级") in ("重大风险", "较大风险")
            ),
            "status_counts": status_counts,
            "active_items": [
                {
                    "id": row.get("id"),
                    "作业票编号": row.get("作业票编号"),
                    "作业内容": row.get("作业内容"),
                    "作业区域": row.get("作业区域"),
                    "风险等级": row.get("风险等级"),
                    "监护人员": row.get("监护人员"),
                    "实际开工时间": row.get("实际开工时间"),
                }
                for row in active_rows
            ],
        }
