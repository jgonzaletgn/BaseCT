import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple
from datetime import datetime

from constants import DB_PATH

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

FIELD_TYPES = ("text", "number", "date", "bool", "file", "select", "relation", "path", "image")

@dataclass
class ProjectMeta:
    id: int
    name: str
    color: str
    created_at: str
    updated_at: str

@dataclass
class TableMeta:
    id: int
    project_id: Optional[int]
    name: str
    created_at: str
    updated_at: str

@dataclass
class FieldMeta:
    id: int
    table_id: int
    name: str
    ftype: str
    required: int
    active: int
    position: int
    options_json: str
    created_at: str
    updated_at: str

class MetaRepository:
    """
    Metadatos:
      - meta_projects: proyectos (agrupación de tablas)
      - meta_tables: tablas (con project_id opcional)
      - meta_fields: campos (con posición para reordenación)
      - meta_table_prefs: preferencias UI por tabla (orden/ocultos, etc.)
    Datos:
      - data_<table_id>: filas
    """
    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_db()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ---------- migrations / schema ----------
    def _has_column(self, table: str, col: str) -> bool:
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA table_info({table});")
        return any(r[1] == col for r in cur.fetchall())

    def _init_db(self):
        cur = self.conn.cursor()

        # Projects
        cur.execute("""
        CREATE TABLE IF NOT EXISTS meta_projects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            parent_id INTEGER NULL,
            color TEXT NOT NULL DEFAULT '#4C9AFF',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(parent_id) REFERENCES meta_projects(id) ON DELETE SET NULL
        );
        """)

        # Migration: add parent_id to projects (subprojects)
        try:
            cur.execute("ALTER TABLE meta_projects ADD COLUMN parent_id INTEGER NULL;")
        except sqlite3.OperationalError:
            pass
        cur.execute("CREATE INDEX IF NOT EXISTS idx_projects_parent ON meta_projects(parent_id);")

        # Tables (older versions might not include project_id)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS meta_tables(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            project_id INTEGER NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES meta_projects(id) ON DELETE SET NULL
        );
        """)
        if not self._has_column("meta_tables", "project_id"):
            cur.execute("ALTER TABLE meta_tables ADD COLUMN project_id INTEGER NULL;")

        # Fields (older versions might not include position)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS meta_fields(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            ftype TEXT NOT NULL,
            required INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            position INTEGER NULL,
            options_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(table_id) REFERENCES meta_tables(id) ON DELETE CASCADE
        );
        """)
        if not self._has_column("meta_fields", "position"):
            cur.execute("ALTER TABLE meta_fields ADD COLUMN position INTEGER NULL;")

        # Table prefs (UI)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS meta_table_prefs(
            table_id INTEGER PRIMARY KEY,
            prefs_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(table_id) REFERENCES meta_tables(id) ON DELETE CASCADE
        );
        """)

        
        # Views (saved table views)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS meta_views(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            view_json TEXT NOT NULL DEFAULT '{}',
            position INTEGER NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(table_id, name),
            FOREIGN KEY(table_id) REFERENCES meta_tables(id) ON DELETE CASCADE
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_views_table ON meta_views(table_id);")

        # Backfill positions for views
        cur.execute("""
            UPDATE meta_views
            SET position = id
            WHERE position IS NULL;
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fields_table ON meta_fields(table_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fields_active ON meta_fields(active);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tables_project ON meta_tables(project_id);")

        # Backfill positions (if null)
        cur.execute("""
            UPDATE meta_fields
            SET position = id
            WHERE position IS NULL;
        """)
        self.conn.commit()

    # ---------- data tables ----------
    def _data_table_name(self, table_id: int) -> str:
        return f"data_{int(table_id)}"

    def _ensure_data_table(self, table_id: int):
        tname = self._data_table_name(table_id)
        cur = self.conn.cursor()
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {tname}(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{tname}_updated ON {tname}(updated_at);")
        self.conn.commit()

    def _table_columns(self, table_name: str) -> set[str]:
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name});")
        return {r[1] for r in cur.fetchall()}

    def _ensure_column(self, table_name: str, col: str, ddl_type: str):
        cols = self._table_columns(table_name)
        if col in cols:
            return
        cur = self.conn.cursor()
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {ddl_type};")
        self.conn.commit()

    def _ddl_for_field(self, ftype: str) -> str:
        if ftype == "text":
            return "TEXT NOT NULL DEFAULT ''"
        if ftype == "number":
            return "REAL NOT NULL DEFAULT 0"
        if ftype == "date":
            return "TEXT NOT NULL DEFAULT ''"
        if ftype == "bool":
            return "INTEGER NOT NULL DEFAULT 0"
        if ftype == "file":
            return "TEXT NOT NULL DEFAULT ''"
        if ftype == "image":
            return "TEXT NOT NULL DEFAULT ''"
        if ftype == "path":
            return "TEXT NOT NULL DEFAULT ''"
        if ftype == "select":
            return "TEXT NOT NULL DEFAULT ''"
        if ftype == "relation":
            return "INTEGER NOT NULL DEFAULT 0"
        raise ValueError(f"Tipo no soportado: {ftype}")

    # ---------- projects ----------
    def list_projects(self) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, parent_id, color, created_at, updated_at FROM meta_projects ORDER BY name COLLATE NOCASE;")
        return cur.fetchall()

    def create_project(self, name: str, color: str = "#4C9AFF", parent_id: Optional[int] = None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre del proyecto es obligatorio.")
        color = (color or "#4C9AFF").strip() or "#4C9AFF"
        ts = now_iso()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO meta_projects(name, parent_id, color, created_at, updated_at) VALUES (?,?,?,?,?);",
            (name, int(parent_id) if parent_id is not None else None, color, ts, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_project(self, project_id: int, name: Optional[str] = None, color: Optional[str] = None, parent_id: Optional[int] = None):
        fields = []
        params: List[Any] = []
        if name is not None:
            name = (name or "").strip()
            if not name:
                raise ValueError("El nombre del proyecto es obligatorio.")
            fields.append("name=?")
            params.append(name)
        if color is not None:
            color = (color or "").strip() or "#4C9AFF"
            fields.append("color=?")
            params.append(color)
        if not fields:
            return
        fields.append("updated_at=?")
        params.append(now_iso())
        params.append(int(project_id))
        cur = self.conn.cursor()
        cur.execute(f"UPDATE meta_projects SET {', '.join(fields)} WHERE id=?;", tuple(params))
        self.conn.commit()

    def delete_project(self, project_id: int):
        # delete children first (subprojects)
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM meta_projects WHERE parent_id=?;", (int(project_id),))
        children = [int(r[0]) for r in cur.fetchall()]
        for cid in children:
            self.delete_project(cid)

        cur = self.conn.cursor()
        cur.execute("UPDATE meta_tables SET project_id=NULL, updated_at=? WHERE project_id=?;", (now_iso(), int(project_id)))
        cur.execute("DELETE FROM meta_projects WHERE id=?;", (int(project_id),))
        self.conn.commit()

    # ---------- tables ----------
    def list_tables(self) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, project_id, created_at, updated_at FROM meta_tables ORDER BY name COLLATE NOCASE;")
        return cur.fetchall()

    def get_table(self, table_id: int) -> sqlite3.Row:
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, project_id, created_at, updated_at FROM meta_tables WHERE id=?;", (int(table_id),))
        r = cur.fetchone()
        if not r:
            raise KeyError("Tabla no encontrada.")
        return r

    def create_table(self, name: str, project_id: Optional[int] = None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre de la tabla es obligatorio.")
        ts = now_iso()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO meta_tables(name, project_id, created_at, updated_at) VALUES(?,?,?,?);",
            (name, int(project_id) if project_id is not None else None, ts, ts),
        )
        self.conn.commit()
        table_id = int(cur.lastrowid)
        self._ensure_data_table(table_id)
        return table_id

    def rename_table(self, table_id: int, new_name: str):
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("El nombre de la tabla es obligatorio.")
        cur = self.conn.cursor()
        cur.execute("UPDATE meta_tables SET name=?, updated_at=? WHERE id=?;", (new_name, now_iso(), int(table_id)))
        self.conn.commit()

    def set_table_project(self, table_id: int, project_id: Optional[int]):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE meta_tables SET project_id=?, updated_at=? WHERE id=?;",
            (int(project_id) if project_id is not None else None, now_iso(), int(table_id)),
        )
        self.conn.commit()

    def delete_table(self, table_id: int):
        tname = self._data_table_name(table_id)
        cur = self.conn.cursor()
        cur.execute("DELETE FROM meta_tables WHERE id=?;", (int(table_id),))
        cur.execute(f"DROP TABLE IF EXISTS {tname};")
        self.conn.commit()

    # ---------- table prefs ----------
    def get_table_prefs(self, table_id: int) -> dict:
        cur = self.conn.cursor()
        cur.execute("SELECT prefs_json FROM meta_table_prefs WHERE table_id=?;", (int(table_id),))
        r = cur.fetchone()
        if not r:
            return {}
        try:
            return json.loads(r["prefs_json"] or "{}")
        except Exception:
            return {}

    def save_table_prefs(self, table_id: int, prefs: dict):
        ts = now_iso()
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO meta_table_prefs(table_id, prefs_json, updated_at)
            VALUES (?,?,?)
            ON CONFLICT(table_id) DO UPDATE SET
                prefs_json=excluded.prefs_json,
                updated_at=excluded.updated_at;
        """, (int(table_id), json.dumps(prefs or {}, ensure_ascii=False), ts))
        self.conn.commit()

    

    # ---------- views (saved table views) ----------
    def list_views(self, table_id: int) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, table_id, name, view_json, position, created_at, updated_at
            FROM meta_views
            WHERE table_id=?
            ORDER BY COALESCE(position, id) ASC, id ASC;
        """, (int(table_id),))
        return cur.fetchall()

    def get_view(self, view_id: int) -> sqlite3.Row:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, table_id, name, view_json, position, created_at, updated_at
            FROM meta_views
            WHERE id=?;
        """, (int(view_id),))
        r = cur.fetchone()
        if not r:
            raise KeyError("Vista no encontrada.")
        return r

    def create_view(self, table_id: int, name: str, view: dict) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre de la vista es obligatorio.")
        ts = now_iso()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO meta_views(table_id, name, view_json, position, created_at, updated_at) VALUES (?,?,?,?,?,?);",
            (int(table_id), name, json.dumps(view or {}, ensure_ascii=False), None, ts, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_view(self, view_id: int, name: Optional[str] = None, view: Optional[dict] = None):
        fields = []
        params: List[Any] = []
        if name is not None:
            name = (name or "").strip()
            if not name:
                raise ValueError("El nombre de la vista es obligatorio.")
            fields.append("name=?")
            params.append(name)
        if view is not None:
            fields.append("view_json=?")
            params.append(json.dumps(view or {}, ensure_ascii=False))
        if not fields:
            return
        fields.append("updated_at=?")
        params.append(now_iso())
        params.append(int(view_id))
        cur = self.conn.cursor()
        cur.execute(f"UPDATE meta_views SET {', '.join(fields)} WHERE id=?;", tuple(params))
        self.conn.commit()

    def delete_view(self, view_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM meta_views WHERE id=?;", (int(view_id),))
        self.conn.commit()
# ---------- fields ----------
    def list_fields(self, table_id: int, active_only: bool = True) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        sql = """
            SELECT id, table_id, name, ftype, required, active, position, options_json, created_at, updated_at
            FROM meta_fields
            WHERE table_id = ?
        """
        params = [int(table_id)]
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY COALESCE(position, id) ASC, id ASC;"
        cur.execute(sql, tuple(params))
        return cur.fetchall()

    def _next_field_position(self, table_id: int) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COALESCE(MAX(COALESCE(position, id)), 0) AS m FROM meta_fields WHERE table_id=?;", (int(table_id),))
        r = cur.fetchone()
        return int(r["m"] or 0) + 1

    def add_field(self, table_id: int, name: str, ftype: str, required: bool = False, options: Optional[dict] = None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre del campo es obligatorio.")
        if ftype not in FIELD_TYPES:
            raise ValueError(f"Tipo inválido. Usa: {', '.join(FIELD_TYPES)}")

        options = options or {}
        if ftype == "select":
            opts = options.get("options", [])
            if not isinstance(opts, list) or not all(isinstance(x, str) for x in opts):
                raise ValueError("En 'select', options debe ser una lista de strings (options=['A','B']).")
        if ftype == "relation":
            if (not isinstance(options.get("target_table_id", None), int)) or int(options.get("target_table_id") or 0) <= 0:
                raise ValueError("En 'relation' debes indicar target_table_id (>0).")
            if "display_field_id" in options and not isinstance(options["display_field_id"], int):
                raise ValueError("display_field_id debe ser int (o 0).")

        ts = now_iso()
        pos = self._next_field_position(int(table_id))
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO meta_fields(table_id, name, ftype, required, active, position, options_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?);
        """, (
            int(table_id), name, ftype, 1 if required else 0, 1, int(pos),
            json.dumps(options, ensure_ascii=False), ts, ts
        ))
        self.conn.commit()
        field_id = int(cur.lastrowid)

        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))
        col = f"f_{field_id}"
        self._ensure_column(tname, col, self._ddl_for_field(ftype))
        return field_id

    def rename_field(self, field_id: int, new_name: str):
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("El nombre del campo es obligatorio.")
        cur = self.conn.cursor()
        cur.execute("UPDATE meta_fields SET name=?, updated_at=? WHERE id=?;", (new_name, now_iso(), int(field_id)))
        self.conn.commit()

    def deactivate_field(self, field_id: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE meta_fields SET active=0, updated_at=? WHERE id=?;", (now_iso(), int(field_id)))
        self.conn.commit()

    def reorder_fields(self, table_id: int, ordered_field_ids: List[int]):
        """
        ordered_field_ids: lista de field_id activos en el orden deseado.
        """
        ids = [int(x) for x in ordered_field_ids if int(x) > 0]
        if not ids:
            return
        cur = self.conn.cursor()
        # Only update fields for that table
        for i, fid in enumerate(ids, start=1):
            cur.execute("UPDATE meta_fields SET position=?, updated_at=? WHERE id=? AND table_id=?;", (i, now_iso(), int(fid), int(table_id)))
        self.conn.commit()

    # ---------- records helpers (relations) ----------
    def get_record_by_id(self, table_id: int, record_id: int) -> Optional[sqlite3.Row]:
        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))
        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM {tname} WHERE id=?;", (int(record_id),))
        return cur.fetchone()

    def get_display_map(self, table_id: int, display_field_id: int, record_ids: List[int]) -> Dict[int, str]:
        ids = [int(x) for x in record_ids if int(x) > 0]
        if not ids:
            return {}
        if int(display_field_id) == 0:
            return {i: f"#{i}" for i in ids}

        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))
        col = f"f_{int(display_field_id)}"
        ph = ",".join(["?"] * len(ids))
        cur = self.conn.cursor()
        cur.execute(f"SELECT id, {col} AS label FROM {tname} WHERE id IN ({ph});", tuple(ids))
        out = {}
        for r in cur.fetchall():
            out[int(r["id"])] = str(r["label"] or f"#{int(r['id'])}")
        for i in ids:
            out.setdefault(i, f"#{i}")
        return out

    def list_relation_options(self, target_table_id: int, display_field_id: int, limit: int = 2000) -> List[Tuple[int, str]]:
        self._ensure_data_table(int(target_table_id))
        tname = self._data_table_name(int(target_table_id))
        cur = self.conn.cursor()
        if int(display_field_id) == 0:
            cur.execute(f"SELECT id FROM {tname} ORDER BY id DESC LIMIT ?;", (int(limit),))
            return [(int(r["id"]), f"#{int(r['id'])}") for r in cur.fetchall()]
        col = f"f_{int(display_field_id)}"
        cur.execute(f"SELECT id, {col} AS label FROM {tname} ORDER BY id DESC LIMIT ?;", (int(limit),))
        out = []
        for r in cur.fetchall():
            rid = int(r["id"])
            lbl = str(r["label"] or f"#{rid}")
            out.append((rid, lbl))
        return out

    # ---------- records (filters/sort) ----------
    def list_records(
        self,
        table_id: int,
        query: str = "",
        limit: int = 500,
        filters: Optional[dict] = None,
        sort_field_id: Optional[int] = None,
        sort_dir: str = "DESC",
    ) -> List[sqlite3.Row]:
        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))
        fields = self.list_fields(int(table_id), active_only=True)
        fields_by_id = {int(f["id"]): f for f in fields}

        where: List[str] = []
        params: List[Any] = []

        q = (query or "").strip()
        if q:
            like = f"%{q}%"
            where_or = ["CAST(id AS TEXT) LIKE ?"]
            params.append(like)

            for f in fields:
                col = f"f_{int(f['id'])}"
                if f["ftype"] in ("text", "date", "file", "select", "path"):
                    where_or.append(f"{col} LIKE ?")
                    params.append(like)
                elif f["ftype"] == "number":
                    try:
                        num = float(q.replace(",", "."))
                        where_or.append(f"{col} = ?")
                        params.append(num)
                    except Exception:
                        pass
                elif f["ftype"] == "bool":
                    if q.lower() in ("si", "sí", "true", "1", "yes"):
                        where_or.append(f"{col} = 1")
                    elif q.lower() in ("no", "false", "0"):
                        where_or.append(f"{col} = 0")
                elif f["ftype"] == "relation":
                    try:
                        rid = int(q)
                        where_or.append(f"{col} = ?")
                        params.append(rid)
                    except Exception:
                        pass
            where.append("(" + " OR ".join(where_or) + ")")

        filters = filters or {}
        for fid_str, fval in list(filters.items()):
            try:
                fid = int(fid_str)
            except Exception:
                continue
            if fid not in fields_by_id:
                continue
            f = fields_by_id[fid]
            col = f"f_{fid}"
            ftype = f["ftype"]
            if not isinstance(fval, dict):
                continue

            if ftype in ("text", "file", "select", "path"):
                if "equals" in fval and str(fval["equals"]).strip() != "":
                    where.append(f"{col} = ?")
                    params.append(str(fval["equals"]))
                elif "contains" in fval and str(fval["contains"]).strip() != "":
                    where.append(f"{col} LIKE ?")
                    params.append(f"%{str(fval['contains'])}%")

            elif ftype == "number":
                if fval.get("min", None) is not None:
                    where.append(f"{col} >= ?")
                    params.append(float(fval["min"]))
                if fval.get("max", None) is not None:
                    where.append(f"{col} <= ?")
                    params.append(float(fval["max"]))

            elif ftype == "date":
                if str(fval.get("from", "")).strip():
                    where.append(f"{col} >= ?")
                    params.append(str(fval["from"]))
                if str(fval.get("to", "")).strip():
                    where.append(f"{col} <= ?")
                    params.append(str(fval["to"]))

            elif ftype == "bool":
                if "is" in fval and fval["is"] in (0, 1):
                    where.append(f"{col} = ?")
                    params.append(int(fval["is"]))

            elif ftype == "relation":
                if "is" in fval and int(fval["is"] or 0) > 0:
                    where.append(f"{col} = ?")
                    params.append(int(fval["is"]))

        order_col = "id"
        if sort_field_id is not None:
            sfid = int(sort_field_id)
            if sfid in fields_by_id:
                order_col = f"f_{sfid}"
        sort_dir = (sort_dir or "DESC").upper()
        if sort_dir not in ("ASC", "DESC"):
            sort_dir = "DESC"

        sql = f"SELECT * FROM {tname}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order_col} {sort_dir}, id DESC LIMIT ?;"
        params.append(int(limit))

        cur = self.conn.cursor()
        cur.execute(sql, tuple(params))
        return cur.fetchall()

    def add_record(self, table_id: int, values_by_field_id: Dict[int, Any]) -> int:
        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))

        cols = ["created_at", "updated_at"]
        vals: List[Any] = [now_iso(), now_iso()]
        for fid, v in values_by_field_id.items():
            cols.append(f"f_{int(fid)}")
            vals.append(v)

        ph = ",".join(["?"] * len(cols))
        sql = f"INSERT INTO {tname}({', '.join(cols)}) VALUES({ph});"
        cur = self.conn.cursor()
        cur.execute(sql, tuple(vals))
        self.conn.commit()
        return int(cur.lastrowid)

    

    def add_record_with_id(
        self,
        table_id: int,
        record_id: int,
        values_by_field_id: Dict[int, Any],
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> int:
        """
        Inserta un registro forzando el ID (útil para Undo/Redo).
        SQLite permite insertar un id explícito en AUTOINCREMENT.
        """
        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))

        cols = ["id", "created_at", "updated_at"]
        vals: List[Any] = [int(record_id), created_at or now_iso(), updated_at or now_iso()]
        for fid, v in values_by_field_id.items():
            cols.append(f"f_{int(fid)}")
            vals.append(v)

        ph = ",".join(["?"] * len(cols))
        sql = f"INSERT OR REPLACE INTO {tname}({', '.join(cols)}) VALUES({ph});"
        cur = self.conn.cursor()
        cur.execute(sql, tuple(vals))
        self.conn.commit()
        return int(record_id)
    def update_record(self, table_id: int, record_id: int, values_by_field_id: Dict[int, Any]):
        if not values_by_field_id:
            return
        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))

        sets = ["updated_at=?"]
        params: List[Any] = [now_iso()]
        for fid, v in values_by_field_id.items():
            sets.append(f"f_{int(fid)}=?")
            params.append(v)
        params.append(int(record_id))

        sql = f"UPDATE {tname} SET {', '.join(sets)} WHERE id=?;"
        cur = self.conn.cursor()
        cur.execute(sql, tuple(params))
        self.conn.commit()

    def delete_record(self, table_id: int, record_id: int):
        self._ensure_data_table(int(table_id))
        tname = self._data_table_name(int(table_id))
        cur = self.conn.cursor()
        cur.execute(f"DELETE FROM {tname} WHERE id=?;", (int(record_id),))
        self.conn.commit()