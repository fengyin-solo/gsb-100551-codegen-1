"""人员资质档案的持久化仓库。

用 SQLite 落地（标准库自带），数据文件固定在 backend/data/qualification.db：
服务重启、页面重新进入，读到的都是同一份档案。上岗名册与队组待办存在同一个库，
复训结论引起的名册变更与待办写入放在同一个事务里提交，随后读到的必然是同一份状态。

老记录处理：首次建库时把历史人员按「入场日期」回填备案日期，过往证书沿用原有
有效期起止，不重算、不延长。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "qualification.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    emp_no TEXT NOT NULL UNIQUE,
    entry_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    filed_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '日常备案'
);
CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    category TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT '新发'
);
CREATE TABLE IF NOT EXISTS roster (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    person_id INTEGER NOT NULL REFERENCES persons(id),
    state TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE (team_id, person_id)
);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    person_id INTEGER REFERENCES persons(id),
    content TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

SEED_TEAMS = ["运维一队", "运维二队", "电气检修队"]

# 老记录：(姓名, 工号, 入场日期)
SEED_PERSONS = [
    ("王建国", "W001", "2023-03-15"),
    ("李海峰", "W002", "2022-06-01"),
    ("张立军", "W003", "2023-09-20"),
    ("赵永强", "W004", "2024-02-01"),
    ("刘明远", "W005", "2023-05-10"),
    ("陈志远", "W006", "2025-01-05"),
]

# 备案记录：(工号, 队组, 备案日期, 来源)；老记录的备案日期按入场日期回填。
# 张立军先在运维一队、后备案到运维二队：归属按最近一次备案算。
SEED_FILINGS = [
    ("W001", "运维一队", "2023-03-15", "入场回填"),
    ("W002", "运维一队", "2022-06-01", "入场回填"),
    ("W003", "运维一队", "2023-09-20", "入场回填"),
    ("W003", "运维二队", "2025-04-10", "日常备案"),
    ("W004", "运维二队", "2024-02-01", "入场回填"),
    ("W005", "电气检修队", "2023-05-10", "入场回填"),
    ("W006", "运维一队", "2025-01-05", "入场回填"),
]

# 过往证书：(工号, 证书类别, 有效期起, 有效期止, 来源)，有效期沿用原有记录。
SEED_CERTIFICATES = [
    ("W001", "高压电工证", "2024-04-01", "2027-04-01", "历史沿用"),
    ("W001", "低压电工证", "2023-04-01", "2026-04-01", "历史沿用"),
    ("W002", "高压电工证", "2022-06-15", "2025-06-15", "历史沿用"),
    ("W003", "登高作业证", "2024-03-01", "2027-03-01", "历史沿用"),
    ("W004", "高压电工证", "2024-02-20", "2026-10-20", "历史沿用"),
    ("W005", "继电保护证", "2023-06-01", "2026-06-01", "历史沿用"),
    ("W006", "低压电工证", "2025-01-20", "2028-01-20", "历史沿用"),
]

# 上岗名册：(工号, 队组, 状态, 原因, 更新时间)。刘明远复训未过关，已摘除。
SEED_ROSTER = [
    ("W001", "运维一队", "在册", "入场回填", "2023-03-15"),
    ("W002", "运维一队", "在册", "入场回填", "2022-06-01"),
    ("W003", "运维二队", "在册", "日常备案", "2025-04-10"),
    ("W004", "运维二队", "在册", "入场回填", "2024-02-01"),
    ("W005", "电气检修队", "已摘除", "复训未过关", "2026-06-20"),
    ("W006", "运维一队", "在册", "复训过关", "2026-09-01"),
]

# 队组待办：(工号, 队组, 内容, 复训结论, 状态, 时间)。复训结论都会写进队组待办。
SEED_TODOS = [
    ("W005", "电气检修队",
     "刘明远「继电保护证」复训未过关，已自动移出本队组上岗名册；需重新培训并复训合格后方可恢复。",
     "未过关", "待处理", "2026-06-20"),
    ("W006", "运维一队",
     "陈志远「低压电工证」复训过关，名册状态保持「在册」。",
     "过关", "已办结", "2026-09-01"),
]


class QualificationDB:
    """人员资质档案的 SQLite 仓库：所有读写走同一个连接，避免读到不一致的副本。"""

    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.RLock()
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)
        self._seed_if_empty()

    # ---------- 初始化 ----------

    def _seed_if_empty(self) -> None:
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
            if count:
                return
            with self._conn:
                for name in SEED_TEAMS:
                    self._conn.execute("INSERT INTO teams (name) VALUES (?)", (name,))
                person_ids: dict[str, int] = {}
                for name, emp_no, entry_date in SEED_PERSONS:
                    cur = self._conn.execute(
                        "INSERT INTO persons (name, emp_no, entry_date) VALUES (?, ?, ?)",
                        (name, emp_no, entry_date),
                    )
                    person_ids[emp_no] = int(cur.lastrowid)
                for emp_no, team, filed_at, source in SEED_FILINGS:
                    self._conn.execute(
                        "INSERT INTO filings (person_id, team_id, filed_at, source) VALUES (?, ?, ?, ?)",
                        (person_ids[emp_no], self._team_id(team), filed_at, source),
                    )
                for emp_no, category, valid_from, valid_to, origin in SEED_CERTIFICATES:
                    self._conn.execute(
                        "INSERT INTO certificates (person_id, category, valid_from, valid_to, origin)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (person_ids[emp_no], category, valid_from, valid_to, origin),
                    )
                for emp_no, team, state, reason, updated_at in SEED_ROSTER:
                    self._conn.execute(
                        "INSERT INTO roster (team_id, person_id, state, reason, updated_at)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (self._team_id(team), person_ids[emp_no], state, reason, updated_at),
                    )
                for emp_no, team, content, conclusion, status, created_at in SEED_TODOS:
                    self._conn.execute(
                        "INSERT INTO todos (team_id, person_id, content, conclusion, status, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (self._team_id(team), person_ids[emp_no], content, conclusion, status, created_at),
                    )

    # ---------- 基础查询 ----------

    def _team_id(self, name: str) -> int:
        row = self._conn.execute("SELECT id FROM teams WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"队组「{name}」不存在")
        return int(row["id"])

    def list_teams(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM teams ORDER BY id").fetchall()
        return [str(row["name"]) for row in rows]

    def team_exists(self, name: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM teams WHERE name = ?", (name,)).fetchone()
        return row is not None

    def list_persons(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, name, emp_no, entry_date FROM persons ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def find_person(self, person_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, name, emp_no, entry_date FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_person_by_emp_no(self, emp_no: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, name, emp_no, entry_date FROM persons WHERE emp_no = ?", (emp_no,)
        ).fetchone()
        return dict(row) if row else None

    def find_person_by_name(self, name: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, name, emp_no, entry_date FROM persons WHERE name = ? ORDER BY id",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    def latest_filing(self, person_id: int) -> dict[str, Any] | None:
        """一个人同时在两个队组备案时，归属按最近一次备案算。"""
        row = self._conn.execute(
            "SELECT f.filed_at, f.source, t.name AS team_name"
            " FROM filings f JOIN teams t ON t.id = f.team_id"
            " WHERE f.person_id = ?"
            " ORDER BY f.filed_at DESC, f.id DESC LIMIT 1",
            (person_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_filings(self, person_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT f.filed_at, f.source, t.name AS team_name"
            " FROM filings f JOIN teams t ON t.id = f.team_id"
            " WHERE f.person_id = ? ORDER BY f.filed_at DESC, f.id DESC",
            (person_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_certificates(self, person_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT category, valid_from, valid_to, origin FROM certificates"
            " WHERE person_id = ? ORDER BY valid_to",
            (person_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def roster_entry(self, team: str, person_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT r.state, r.reason, r.updated_at FROM roster r"
            " JOIN teams t ON t.id = r.team_id"
            " WHERE t.name = ? AND r.person_id = ?",
            (team, person_id),
        ).fetchone()
        return dict(row) if row else None

    def list_roster(self, team: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT p.name, p.emp_no, r.state, r.reason, r.updated_at, r.person_id"
            " FROM roster r"
            " JOIN teams t ON t.id = r.team_id"
            " JOIN persons p ON p.id = r.person_id"
            " WHERE t.name = ? ORDER BY r.state, p.emp_no",
            (team,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_todos(self, team: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT d.id, p.name AS person_name, d.content, d.conclusion, d.status, d.created_at"
            " FROM todos d"
            " JOIN teams t ON t.id = d.team_id"
            " LEFT JOIN persons p ON p.id = d.person_id"
            " WHERE t.name = ? ORDER BY d.status DESC, d.id DESC",
            (team,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ---------- 写入 ----------

    def create_filing(
        self,
        *,
        name: str,
        emp_no: str,
        entry_date: str,
        team: str,
        filed_at: str,
        source: str,
        certificate: dict[str, str] | None,
        today: str,
    ) -> int:
        """登记一次备案：人员不存在则建档；名册按 (队组, 人员) 归位为「在册」。"""
        with self._lock, self._conn:
            person = self.find_person_by_emp_no(emp_no) if emp_no else None
            if person is None:
                person = self.find_person_by_name(name)
            if person is None:
                cur = self._conn.execute(
                    "INSERT INTO persons (name, emp_no, entry_date) VALUES (?, ?, ?)",
                    (name, emp_no, entry_date),
                )
                person_id = int(cur.lastrowid)
            else:
                person_id = int(person["id"])
            self._conn.execute(
                "INSERT INTO filings (person_id, team_id, filed_at, source) VALUES (?, ?, ?, ?)",
                (person_id, self._team_id(team), filed_at, source),
            )
            if certificate is not None:
                self._conn.execute(
                    "INSERT INTO certificates (person_id, category, valid_from, valid_to, origin)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        person_id,
                        certificate["category"],
                        certificate["valid_from"],
                        certificate["valid_to"],
                        certificate["origin"],
                    ),
                )
            self._conn.execute(
                "INSERT INTO roster (team_id, person_id, state, reason, updated_at)"
                " VALUES (?, ?, '在册', ?, ?)"
                " ON CONFLICT (team_id, person_id)"
                " DO UPDATE SET state = '在册', reason = excluded.reason, updated_at = excluded.updated_at",
                (self._team_id(team), person_id, source, today),
            )
        return person_id

    def record_retraining(
        self,
        *,
        team: str,
        person_id: int,
        category: str,
        conclusion: str,
        content: str,
        today: str,
    ) -> None:
        """复训结论落库：名册变更与待办写入在同一个事务里，随后读到的得是同一份。"""
        on_roster = conclusion != "未过关"
        state = "在册" if on_roster else "已摘除"
        reason = f"复训{conclusion}"
        todo_status = "已办结" if on_roster else "待处理"
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO roster (team_id, person_id, state, reason, updated_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (team_id, person_id)"
                " DO UPDATE SET state = excluded.state, reason = excluded.reason,"
                "               updated_at = excluded.updated_at",
                (self._team_id(team), person_id, state, reason, today),
            )
            self._conn.execute(
                "INSERT INTO todos (team_id, person_id, content, conclusion, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (self._team_id(team), person_id, content, conclusion, todo_status, today),
            )


qualification_db = QualificationDB()
