"""人员资质档案业务规则：备案归属、名册流转、复训结论与队组权限都收在这里。

核心口径：
- 一个人同时在两个队组备案时，所属队组按最近一次备案算；
- 复训未过关 → 自动从本队组上岗名册摘除，结论同时写入队组待办（同一事务）；
- 名册之外的人不许被工作票选中；
- 跨队组只读：写操作按队组归属判定权限，越权当场打回并写清缺哪一项授权；
- 老记录按入场日期回填备案日期，过往证书沿用原有有效期。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.qualification_db import QualificationDB, qualification_db

CONCLUSIONS = ["过关", "未过关"]
EXPIRING_DAYS = 30
FILING_REQUIRED = ["姓名", "队组"]
RETRAINING_REQUIRED = ["姓名", "队组", "证书类别", "复训结论"]


class PermissionDenied(Exception):
    """越权提交：消息里必须写清缺哪一项授权。"""


def _cert_status(valid_to: str, today: date) -> str:
    end = date.fromisoformat(valid_to)
    if end < today:
        return "已过期"
    if (end - today).days <= EXPIRING_DAYS:
        return "临期"
    return "有效"


class QualificationService:
    def __init__(self, db: QualificationDB | None = None) -> None:
        self.db = db or qualification_db

    # ---------- 权限 ----------

    def _require_write(self, operator_team: str | None, target_team: str) -> None:
        """写操作按队组归属判定：只有本队组能改自己的档案，跨队组一律只读。"""
        if not operator_team or not operator_team.strip():
            raise PermissionDenied(
                "越权提交已打回：缺少授权「当前队组身份」——请求未携带队组标识，无法判定队组归属"
            )
        if operator_team.strip() != target_team:
            raise PermissionDenied(
                f"越权提交已打回：缺少授权「档案修改·{target_team}」——"
                f"当前队组「{operator_team.strip()}」仅持有本队组档案的修改授权，"
                f"「{target_team}」的档案对你只读"
            )

    # ---------- 读取 ----------

    def _cert_view(self, cert: dict[str, Any], today: date) -> dict[str, Any]:
        return {
            "类别": cert["category"],
            "有效期起": cert["valid_from"],
            "有效期止": cert["valid_to"],
            "状态": _cert_status(cert["valid_to"], today),
            "来源": cert["origin"],
        }

    def _archive_row(self, person: dict[str, Any], today: date) -> dict[str, Any]:
        filing = self.db.latest_filing(int(person["id"]))
        team_name = filing["team_name"] if filing else "未备案"
        certs = [self._cert_view(c, today) for c in self.db.list_certificates(int(person["id"]))]
        roster = self.db.roster_entry(team_name, int(person["id"])) if filing else None
        roster_state = roster["state"] if roster else "未入册"
        reason = roster["reason"] if roster else ""
        has_valid_cert = any(c["状态"] != "已过期" for c in certs)
        if roster_state != "在册":
            duty = "不可（不在名册）"
        elif not has_valid_cert:
            duty = "不可（证书均已过期）"
        else:
            duty = "可"
        return {
            "person_id": person["id"],
            "姓名": person["name"],
            "工号": person["emp_no"],
            "入场日期": person["entry_date"],
            "所属队组": team_name,
            "最近备案日期": filing["filed_at"] if filing else "",
            "证书列表": certs,
            "名册状态": roster_state,
            "名册说明": reason,
            "可否持证值班": duty,
        }

    def list_archive(
        self,
        *,
        keyword: str | None = None,
        team: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        today = date.today()
        rows: list[dict[str, Any]] = []
        for person in self.db.list_persons():
            row = self._archive_row(person, today)
            if team and row["所属队组"] != team:
                continue
            if keyword and keyword not in row["姓名"] and keyword not in row["工号"]:
                continue
            rows.append(row)
        # 快过期、已过期的排在前面，值班前一眼能看到谁的证要到期
        rows.sort(key=lambda r: min((c["有效期止"] for c in r["证书列表"]), default="9999-12-31"))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_person(self, person_id: int) -> dict[str, Any] | None:
        person = self.db.find_person(person_id)
        if person is None:
            return None
        row = self._archive_row(person, date.today())
        row["备案记录"] = self.db.list_filings(person_id)
        return row

    def list_roster(self, team: str) -> list[dict[str, Any]]:
        today = date.today()
        rows = []
        for entry in self.db.list_roster(team):
            certs = [
                self._cert_view(c, today)
                for c in self.db.list_certificates(int(entry["person_id"]))
            ]
            has_valid_cert = any(c["状态"] != "已过期" for c in certs)
            nearest = min((c["有效期止"] for c in certs), default="")
            selectable = entry["state"] == "在册"
            rows.append({
                "姓名": entry["name"],
                "工号": entry["emp_no"],
                "名册状态": entry["state"],
                "名册说明": entry["reason"],
                "更新时间": entry["updated_at"],
                "最近证书到期": nearest,
                "证书提示": "、".join(
                    f"{c['类别']}{c['状态']}" for c in certs if c["状态"] != "有效"
                ) or "证书均在有效期内",
                "可被工作票选中": "可" if selectable else "不可（名册之外）",
                "持证值班提示": "证书均已过期，需复训取证" if selectable and not has_valid_cert else "",
            })
        return rows

    def list_todos(self, team: str) -> list[dict[str, Any]]:
        return [
            {
                "id": row["id"],
                "姓名": row["person_name"] or "",
                "内容": row["content"],
                "复训结论": row["conclusion"],
                "状态": row["status"],
                "时间": row["created_at"],
            }
            for row in self.db.list_todos(team)
        ]

    def summary(self) -> list[dict[str, Any]]:
        today = date.today()
        persons = self.db.list_persons()
        expiring = 0
        expired = 0
        for person in persons:
            for cert in self.db.list_certificates(int(person["id"])):
                status = _cert_status(cert["valid_to"], today)
                if status == "临期":
                    expiring += 1
                elif status == "已过期":
                    expired += 1
        pending_todos = sum(
            1 for team in self.db.list_teams() for row in self.db.list_todos(team)
            if row["status"] == "待处理"
        )
        return [
            {"label": "档案人数", "value": len(persons)},
            {"label": f"{EXPIRING_DAYS}天内到期证书", "value": expiring},
            {"label": "已过期证书", "value": expired},
            {"label": "待处理待办", "value": pending_todos},
        ]

    # ---------- 写入 ----------

    def create_filing(
        self, values: dict[str, Any], *, operator_team: str | None
    ) -> tuple[dict[str, Any] | None, str | None]:
        missing = [f for f in FILING_REQUIRED if not str(values.get(f) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        team = str(values["队组"]).strip()
        if not self.db.team_exists(team):
            return None, f"队组「{team}」不存在，可选：{'、'.join(self.db.list_teams())}"
        self._require_write(operator_team, team)

        today = date.today().isoformat()
        name = str(values["姓名"]).strip()
        emp_no = str(values.get("工号") or "").strip()
        entry_date = str(values.get("入场日期") or "").strip()
        filed_at = str(values.get("备案日期") or "").strip()
        if not entry_date:
            entry_date = filed_at or today
        if not filed_at:
            # 老记录没填备案日期时，按入场日期回填
            filed_at = entry_date
        source = "入场回填" if filed_at <= entry_date else "日常备案"

        certificate = None
        category = str(values.get("证书类别") or "").strip()
        if category:
            valid_to = str(values.get("有效期止") or "").strip()
            if not valid_to:
                return None, "填写证书类别时必须给出有效期止；过往证书沿用原有有效期，不代为推算"
            certificate = {
                "category": category,
                "valid_from": str(values.get("有效期起") or "").strip() or filed_at,
                "valid_to": valid_to,
                "origin": "历史沿用" if filed_at < today else "新发",
            }

        if not emp_no:
            emp_no = f"W{date.today():%Y}{name}"  # 缺工号时给个可辨识的占位，便于后续检索
        person_id = self.db.create_filing(
            name=name,
            emp_no=emp_no,
            entry_date=entry_date,
            team=team,
            filed_at=filed_at,
            source=source,
            certificate=certificate,
            today=today,
        )
        person = self.db.find_person(person_id)
        assert person is not None
        return self._archive_row(person, date.today()), None

    def record_retraining(
        self, values: dict[str, Any], *, operator_team: str | None
    ) -> tuple[dict[str, Any] | None, str]:
        missing = [f for f in RETRAINING_REQUIRED if not str(values.get(f) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        team = str(values["队组"]).strip()
        name = str(values["姓名"]).strip()
        category = str(values["证书类别"]).strip()
        conclusion = str(values["复训结论"]).strip()
        if conclusion not in CONCLUSIONS:
            return None, f"复训结论只能是：{'、'.join(CONCLUSIONS)}"
        self._require_write(operator_team, team)

        person = self.db.find_person_by_name(name)
        if person is None:
            return None, f"未找到「{name}」的资质档案，先登记备案再录入复训结论"
        filing = self.db.latest_filing(int(person["id"]))
        if filing is None or filing["team_name"] != team:
            current = filing["team_name"] if filing else "未备案"
            return None, (
                f"「{name}」最近一次备案在「{current}」，"
                f"「{team}」无权也没必要录入其复训结论"
            )

        today = date.today().isoformat()
        if conclusion == "未过关":
            content = (
                f"{name}「{category}」复训未过关，已自动移出本队组上岗名册；"
                f"需重新培训并复训合格后方可恢复。"
            )
        else:
            content = f"{name}「{category}」复训过关，名册状态保持「在册」。"
        self.db.record_retraining(
            team=team,
            person_id=int(person["id"]),
            category=category,
            conclusion=conclusion,
            content=content,
            today=today,
        )
        row = self._archive_row(person, date.today())
        if conclusion == "未过关":
            message = f"复训结论已记录：{name}「{category}」未过关，已自动移出「{team}」上岗名册，结论已写入队组待办"
        else:
            message = f"复训结论已记录：{name}「{category}」过关，名册保持「在册」，结论已写入队组待办"
        return row, message

    def work_ticket_check(self, values: dict[str, Any]) -> tuple[bool, str]:
        """工作票选人校验：名册之外的人不许被工作票选中。"""
        team = str(values.get("队组") or "").strip()
        name = str(values.get("姓名") or "").strip()
        if not team or not name:
            return False, "缺少必填字段：队组、姓名"
        person = self.db.find_person_by_name(name)
        if person is None:
            return False, f"工作票选人打回：「{name}」没有资质档案，不在「{team}」上岗名册内，不许被工作票选中"
        filing = self.db.latest_filing(int(person["id"]))
        current = filing["team_name"] if filing else "未备案"
        if current != team:
            return False, (
                f"工作票选人打回：「{name}」最近一次备案在「{current}」，"
                f"不在「{team}」上岗名册内，不许被工作票选中"
            )
        roster = self.db.roster_entry(team, int(person["id"]))
        if roster is None or roster["state"] != "在册":
            reason = roster["reason"] if roster else "未入册"
            return False, (
                f"工作票选人打回：「{name}」已被移出「{team}」上岗名册（{reason}），不许被工作票选中"
            )
        today = date.today()
        certs = [self._cert_view(c, today) for c in self.db.list_certificates(int(person["id"]))]
        warnings = [f"{c['类别']}{c['状态']}（至{c['有效期止']}）" for c in certs if c["状态"] != "有效"]
        suffix = f"；注意：{'、'.join(warnings)}" if warnings else ""
        return True, f"「{name}」在「{team}」上岗名册内，可被工作票选中{suffix}"
