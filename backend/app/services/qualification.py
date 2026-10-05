"""人员资质档案业务规则：备案口径、复训结论、队组名册与待办、跨队组权限都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "qualification"
TODO_MODULE = "qualification_todo"

TEAMS = ["运维一队", "运维二队", "检修队"]
CERT_TYPES = ["高压电工证", "低压电工证", "高处作业证", "调度受令资格证"]
REQUIRED_FIELDS = ["姓名", "所属队组", "证书类别", "证书有效期至", "入场日期"]
RETRAINING_RESULTS = ["复训通过", "复训未通过"]
STATUS_ACTIVE = "在岗"
STATUS_REMOVED = "已摘牌"


def _today() -> str:
    return date.today().isoformat()


def _cert_state(row: dict[str, Any]) -> str:
    """证书状态只按已登记的有效期判定：过往证书沿用原有有效期，不做重算。"""
    valid_until = str(row.get("证书有效期至") or "").strip()
    if not valid_until:
        return "未登记"
    return "有效" if valid_until >= _today() else "已过期"


def _filing_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("备案时间") or ""), int(row.get("id", 0)))


def _latest_filings() -> dict[str, dict[str, Any]]:
    """按姓名归并备案记录：一个人同时在两个队组时，按最近一次备案算。"""
    latest: dict[str, dict[str, Any]] = {}
    for row in store.rows(MODULE):
        name = str(row.get("姓名") or "").strip()
        if not name:
            continue
        current = latest.get(name)
        if current is None or _filing_key(row) > _filing_key(current):
            latest[name] = row
    return latest


def check_write_permission(operator_team: str, owner_team: str) -> str | None:
    """跨队组只读：写操作要求操作队组与档案所属队组一致，越权时写清缺哪一项授权。"""
    if not operator_team:
        return "缺少授权：未提供操作队组，无法判定队组归属"
    if operator_team != owner_team:
        return f"缺少授权：队组「{operator_team}」对队组「{owner_team}」的档案写权限"
    return None


class QualificationService:
    def meta(self) -> dict[str, Any]:
        return {"teams": TEAMS, "cert_types": CERT_TYPES, "retraining_results": RETRAINING_RESULTS}

    def _enrich(self, row: dict[str, Any], latest: dict[str, dict[str, Any]]) -> dict[str, Any]:
        enriched = dict(row)
        enriched["证书状态"] = _cert_state(row)
        enriched["当前备案"] = latest.get(str(row.get("姓名") or "").strip()) is row
        return enriched

    def list_archives(
        self,
        *,
        keyword: str | None = None,
        team: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("姓名", "")) or keyword in str(row.get("档案编号", ""))
            ]
        if team:
            rows = [row for row in rows if row.get("所属队组") == team]
        rows.sort(key=_filing_key, reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        latest = _latest_filings()
        return [self._enrich(row, latest) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return self._enrich(row, _latest_filings())

    def create_entry(
        self, values: dict[str, Any], operator_team: str
    ) -> tuple[dict[str, Any] | None, list[str], str | None]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, None
        owner_team = str(values.get("所属队组") or "").strip()
        denial = check_write_permission(operator_team, owner_team)
        if denial:
            return None, [], denial
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["档案编号"] = f"ZZ-{entry['id']:04d}"
        for field in REQUIRED_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["证书编号"] = str(values.get("证书编号") or "").strip()
        # 老记录按入场日期回填备案时间；未给入场日期时才落到今天
        entry["备案时间"] = str(values.get("备案时间") or "").strip() or entry["入场日期"] or _today()
        entry["复训结论"] = "待复训"
        entry["status"] = STATUS_ACTIVE
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        store.persist(MODULE)
        return self._enrich(entry, _latest_filings()), [], None

    def record_retraining(
        self, entry_id: int, conclusion: str, operator_team: str
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"资质档案 {entry_id} 不存在或已归档", None
        denial = check_write_permission(operator_team, str(entry.get("所属队组") or ""))
        if denial:
            return None, denial, denial
        if conclusion not in RETRAINING_RESULTS:
            return None, f"复训结论「{conclusion}」不在允许范围（{'、'.join(RETRAINING_RESULTS)}）", None
        entry["复训结论"] = conclusion
        entry["pending"] = False
        passed = conclusion == "复训通过"
        entry["status"] = STATUS_ACTIVE if passed else STATUS_REMOVED
        entry["abnormal"] = not passed
        self._append_todo(entry, conclusion)
        store.persist(MODULE)
        store.persist(TODO_MODULE)
        if passed:
            message = f"{entry['姓名']} 复训通过，结论已写入队组「{entry['所属队组']}」待办列表"
        else:
            message = f"{entry['姓名']} 复训未通过，已从队组「{entry['所属队组']}」上岗名册自动摘除，结论已写入待办列表"
        return self._enrich(entry, _latest_filings()), message, None

    def _append_todo(self, entry: dict[str, Any], conclusion: str) -> dict[str, Any]:
        """复训结论写入所属队组的待办列表，与名册读的是同一份数据。"""
        todos = store.rows(TODO_MODULE)
        passed = conclusion == "复训通过"
        todo = {
            "id": max((int(row.get("id", 0)) for row in todos), default=0) + 1,
            "队组": entry["所属队组"],
            "内容": f"{entry['姓名']}（{entry['证书类别']}）{conclusion}" + ("，可继续持证值班" if passed else "，已从上岗名册摘除，请安排补考复训"),
            "来源": "复训结论",
            "时间": _today(),
            "status": "待处理",
            "pending": True,
            "abnormal": not passed,
        }
        todos.append(todo)
        return todo

    def team_roster(self, team: str) -> list[dict[str, Any]]:
        """上岗名册从档案实时归并：只认最近一次备案，复训未通过的自动摘掉。"""
        roster: list[dict[str, Any]] = []
        for name, row in _latest_filings().items():
            if row.get("所属队组") != team:
                continue
            if row.get("复训结论") == "复训未通过":
                continue
            roster.append({
                "姓名": name,
                "证书类别": row.get("证书类别"),
                "证书编号": row.get("证书编号"),
                "证书有效期至": row.get("证书有效期至"),
                "证书状态": _cert_state(row),
                "备案时间": row.get("备案时间"),
                "复训结论": row.get("复训结论"),
            })
        roster.sort(key=lambda item: str(item["姓名"]))
        return roster

    def team_todos(self, team: str) -> list[dict[str, Any]]:
        return [dict(row) for row in store.rows(TODO_MODULE) if row.get("队组") == team]

    def validate_candidate(self, team: str, name: str) -> tuple[bool, str]:
        """工作票选人校验：名册之外的人不许被工作票选中。"""
        if not name:
            return False, "请先填写工作票拟选人员姓名"
        roster_names = {item["姓名"] for item in self.team_roster(team)}
        if name in roster_names:
            return True, f"{name} 在队组「{team}」上岗名册内，可被工作票选中"
        return False, f"{name} 不在队组「{team}」上岗名册内，工作票不得选中"
