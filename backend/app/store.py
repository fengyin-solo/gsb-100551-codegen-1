"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
人员资质档案这类要求"重新进入仍是同一份"的模块会落到 JSON 文件：
启动时若文件已存在则读回磁盘数据，否则写入种子数据；每次变更后同步落盘。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.seed import SEED_ROWS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PERSISTED_MODULES = {"qualification", "qualification_todo"}


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: self._load(name, rows) for name, rows in SEED_ROWS.items()
        }

    def _load(self, module: str, seed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if module not in PERSISTED_MODULES:
            return [dict(row) for row in seed_rows]
        path = DATA_DIR / f"{module}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        rows = [dict(row) for row in seed_rows]
        self._write(module, rows)
        return rows

    def _write(self, module: str, rows: list[dict[str, Any]]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / f"{module}.json"
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def persist(self, module: str) -> None:
        """把持久化模块的当前数据写回磁盘；非持久化模块调用时直接跳过。"""
        if module not in PERSISTED_MODULES:
            return
        with self._lock:
            self._write(module, self.rows(module))

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
