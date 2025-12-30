import csv
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from PySide6.QtCore import Qt, QDate, QUrl, QSize
from PySide6.QtGui import QAction, QDesktopServices, QColor, QPalette, QIcon, QPixmap, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem, QStyledItemDelegate,
    QAbstractItemView, QDialog, QFormLayout, QMessageBox, QFileDialog,
    QDateEdit, QDoubleSpinBox, QCheckBox, QSplitter, QMenu, QTextEdit,
    QGroupBox, QTreeWidget, QTreeWidgetItem, QColorDialog, QInputDialog,
    QHeaderView, QListWidget, QListWidgetItem, QToolBar, QToolButton, QStyle,
    QSizePolicy
)

from repo import MetaRepository, FIELD_TYPES
from utils import normalize_attachment_input
from constants import VAULT_DIR, DB_PATH, APP_NAME, APP_VERSION, APP_RELEASE_DATE, APP_AUTHOR
from i18n import tr, get_language, set_language

# PDF (reportlab)
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# -------------------- Dark mode (palette + stylesheet) --------------------
def build_dark_palette() -> QPalette:
    pal = QPalette()
    # Base colors
    window = QColor("#0B1220")
    base = QColor("#0F172A")          # inputs
    alt = QColor("#111C33")           # alternate rows
    text = QColor("#E5E7EB")
    disabled = QColor("#9CA3AF")
    button = QColor("#111827")
    highlight = QColor("#2563EB")
    highlight_text = QColor("#FFFFFF")
    mid = QColor("#1F2A44")
    shadow = QColor("#000000")

    pal.setColor(QPalette.Window, window)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, alt)
    pal.setColor(QPalette.ToolTipBase, base)
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, button)
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.BrightText, QColor("#EF4444"))
    pal.setColor(QPalette.Highlight, highlight)
    pal.setColor(QPalette.HighlightedText, highlight_text)
    pal.setColor(QPalette.Mid, mid)
    pal.setColor(QPalette.Shadow, shadow)

    # disabled
    pal.setColor(QPalette.Disabled, QPalette.Text, disabled)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, disabled)
    pal.setColor(QPalette.Disabled, QPalette.WindowText, disabled)

    return pal

APP_STYLESHEET = """
/* Global */
QWidget { font-size: 13px; }
QMainWindow { background: #0B1220; }
QToolTip { color: #E5E7EB; background: #0F172A; border: 1px solid #1F2A44; }

/* Buttons */
QPushButton, QToolButton {
  padding: 7px 10px;
  border-radius: 10px;
  background: #111827;
  border: 1px solid #1F2A44;
  color: #E5E7EB;
}
QPushButton:hover, QToolButton:hover { background: #0F172A; }
QPushButton:pressed, QToolButton:pressed { background: #0B1220; }

/* Inputs */
QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QTextEdit {
  padding: 7px;
  border-radius: 10px;
  border: 1px solid #1F2A44;
  background: #0F172A;
  color: #E5E7EB;
  selection-background-color: #2563EB;
  selection-color: #FFFFFF;
}
QComboBox::drop-down { border: 0px; width: 22px; }
QComboBox QAbstractItemView {
  background: #0F172A;
  color: #E5E7EB;
  selection-background-color: #2563EB;
  selection-color: #FFFFFF;
  border: 1px solid #1F2A44;
}

/* Lists, Trees, Tables */
QTreeWidget, QListWidget, QTableWidget {
  border: 1px solid #1F2A44;
  border-radius: 12px;
  background: #0F172A;
  color: #E5E7EB;
  alternate-background-color: #111C33;
  gridline-color: #1F2A44;
}
QHeaderView::section {
  background: #111827;
  color: #E5E7EB;
  padding: 7px;
  border: 0px;
  border-bottom: 1px solid #1F2A44;
  font-weight: 600;
}
QTableWidget::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {
  background: #2563EB;
  color: #FFFFFF;
}
QTableWidget::item { padding: 4px; }

/* Splitter */
QSplitter::handle { background: #1F2A44; }

/* GroupBox */
QGroupBox {
  border: 1px solid #1F2A44;
  border-radius: 12px;
  margin-top: 10px;
  padding: 8px;
  background: #0F172A;
  color: #E5E7EB;
}
QGroupBox:title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }

/* Menu */
QMenu {
  background: #0F172A;
  color: #E5E7EB;
  border: 1px solid #1F2A44;
}
QMenu::item:selected { background: #2563EB; color: #FFFFFF; }
"""


# -------------------- DB backup / restore (impl, attached to MainWindow) --------------------
# -------------------- Tree context menu (impl, attached to MainWindow) --------------------
# -------------------- Field types --------------------
TYPE_LABELS = {
    "text": "Texto",
    "number": "Número",
    "date": "Fecha",
    "bool": "Sí/No",
    "file": "Archivo",
    "select": "Select",
    "relation": "Relación",
    "path": "Ruta/Enlace",
    "image": "Imagen",
}

def parse_field_options_json(field_row) -> dict:
    try:
        return json.loads(field_row["options_json"] or "{}")
    except Exception:
        return {}

def color_icon(hex_color: str, size: int = 10) -> QIcon:
    c = QColor(hex_color)
    if not c.isValid():
        c = QColor("#4C9AFF")
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    from PySide6.QtGui import QPainter
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(0, 0, size, size, 3, 3)
    p.end()
    return QIcon(pix)

# -------------------- dialogs (add field / view) --------------------
class AddFieldDialog(QDialog):
    """
    select: options={"options": [...]}
    relation: options={"target_table_id": int, "display_field_id": int}
    """
    def __init__(self, repo: MetaRepository, current_table_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.current_table_id = int(current_table_id)
        self.setWindowTitle(tr("Añadir campo"))

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.name = QLineEdit()
        self.ftype = QComboBox()
        for t in FIELD_TYPES:
            self.ftype.addItem(TYPE_LABELS[t], t)
        self.required = QCheckBox("Obligatorio")

        form.addRow("Nombre:", self.name)
        form.addRow("Tipo:", self.ftype)
        form.addRow("", self.required)

        # Select options
        self.gb_select = QGroupBox("Opciones de select")
        sel_layout = QVBoxLayout(self.gb_select)
        self.select_help = QLabel(tr("Una opción por línea (o separadas por coma)."))
        self.select_text = QTextEdit()
        self.select_text.setFixedHeight(90)
        sel_layout.addWidget(self.select_help)
        sel_layout.addWidget(self.select_text)

        # Relation options
        self.gb_rel = QGroupBox(tr("Opciones de relación"))
        rel_form = QFormLayout(self.gb_rel)
        self.rel_table = QComboBox()
        self.rel_display = QComboBox()
        rel_form.addRow(tr("Tabla destino:"), self.rel_table)
        rel_form.addRow("Mostrar por:", self.rel_display)

        root.addWidget(self.gb_select)
        root.addWidget(self.gb_rel)

        self._load_relation_tables()
        self.ftype.currentIndexChanged.connect(self._toggle_extra)
        self.rel_table.currentIndexChanged.connect(self._load_relation_display_fields)
        self._toggle_extra()

        btns = QHBoxLayout()
        root.addLayout(btns)
        btns.addStretch(1)
        b_cancel = QPushButton("Cancelar")
        b_ok = QPushButton("Añadir")
        b_ok.setDefault(True)
        btns.addWidget(b_cancel)
        btns.addWidget(b_ok)
        b_cancel.clicked.connect(self.reject)
        b_ok.clicked.connect(self.accept)

    def _load_relation_tables(self):
        self.rel_table.clear()
        tables = self.repo.list_tables()
        for t in tables:
            tid = int(t["id"])
            if tid == self.current_table_id:
                continue
            self.rel_table.addItem(t["name"], tid)
        self._load_relation_display_fields()

    def _load_relation_display_fields(self):
        self.rel_display.clear()
        target_tid = self.rel_table.currentData()
        self.rel_display.addItem("ID", 0)
        if target_tid is None:
            return
        for f in self.repo.list_fields(int(target_tid), active_only=True):
            self.rel_display.addItem(f["name"], int(f["id"]))

    def _toggle_extra(self):
        t = self.ftype.currentData()
        self.gb_select.setVisible(t == "select")
        self.gb_rel.setVisible(t == "relation")

    def get_data(self) -> dict:
        ftype = self.ftype.currentData()
        options = {}
        if ftype == "select":
            raw = self.select_text.toPlainText().strip()
            parts = []
            for line in raw.splitlines():
                for p in line.split(","):
                    s = p.strip()
                    if s:
                        parts.append(s)
            seen, opts = set(), []
            for x in parts:
                if x not in seen:
                    seen.add(x)
                    opts.append(x)
            options = {"options": opts}
        elif ftype == "relation":
            target_tid = self.rel_table.currentData()
            options = {
                "target_table_id": int(target_tid or 0),
                "display_field_id": int(self.rel_display.currentData() or 0),
            }
        return {
            "name": self.name.text().strip(),
            "ftype": ftype,
            "required": self.required.isChecked(),
            "options": options,
        }

class ViewOptionsDialog(QDialog):
    """
    Filtros + ordenación (como en v5).
    """
    def __init__(self, repo: MetaRepository, table_id: int, fields, current_filters=None, current_sort=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.table_id = int(table_id)
        self.fields = fields or []
        self.current_filters = current_filters or {}
        self.current_sort = current_sort or {"field_id": None, "dir": "DESC"}

        self.setWindowTitle(tr("Vista: filtros y ordenación"))
        root = QVBoxLayout(self)

        sort_box = QGroupBox("Ordenar")
        sort_layout = QFormLayout(sort_box)
        self.sort_field = QComboBox()
        self.sort_field.addItem("ID", None)
        for f in self.fields:
            self.sort_field.addItem(f["name"], int(f["id"]))
        self.sort_dir = QComboBox()
        self.sort_dir.addItem("Descendente", "DESC")
        self.sort_dir.addItem("Ascendente", "ASC")

        sfid = self.current_sort.get("field_id", None)
        idx = self.sort_field.findData(sfid)
        if idx >= 0:
            self.sort_field.setCurrentIndex(idx)
        didx = self.sort_dir.findData(self.current_sort.get("dir", "DESC"))
        if didx >= 0:
            self.sort_dir.setCurrentIndex(didx)

        sort_layout.addRow(tr("Campo:"), self.sort_field)
        sort_layout.addRow(tr("Dirección:"), self.sort_dir)
        root.addWidget(sort_box)

        filt_box = QGroupBox("Filtros")
        filt_form = QFormLayout(filt_box)
        self._filter_widgets: Dict[int, Any] = {}

        for f in self.fields:
            fid = int(f["id"])
            ftype = f["ftype"]
            label = f["name"]

            if ftype in ("text", "file", "path"):
                w = QLineEdit()
                w.setPlaceholderText("contiene…")
                cur = self.current_filters.get(str(fid), {}).get("contains", "")
                w.setText(str(cur or ""))
                self._filter_widgets[fid] = ("text_contains", w)
                filt_form.addRow(label + ":", w)

            elif ftype == "select":
                opts = parse_field_options_json(f).get("options", [])
                cb = QComboBox()
                cb.addItem("(cualquiera)", "")
                for o in opts:
                    cb.addItem(o, o)
                cur = self.current_filters.get(str(fid), {}).get("equals", "")
                idx = cb.findData(cur)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                self._filter_widgets[fid] = ("select_equals", cb)
                filt_form.addRow(label + ":", cb)

            elif ftype == "number":
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                chk = QCheckBox("Aplicar")
                mn = QDoubleSpinBox()
                mx = QDoubleSpinBox()
                for s in (mn, mx):
                    s.setRange(-1e12, 1e12)
                    s.setDecimals(2)
                mn.setPrefix("min ")
                mx.setPrefix("max ")
                cur = self.current_filters.get(str(fid), {})
                if cur.get("min") is not None or cur.get("max") is not None:
                    chk.setChecked(True)
                if cur.get("min") is not None:
                    mn.setValue(float(cur["min"]))
                if cur.get("max") is not None:
                    mx.setValue(float(cur["max"]))
                h.addWidget(chk)
                h.addWidget(mn, 1)
                h.addWidget(mx, 1)
                self._filter_widgets[fid] = ("number_range", (chk, mn, mx))
                filt_form.addRow(label + ":", row)

            elif ftype == "date":
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                chk = QCheckBox("Aplicar")
                dfrom = QDateEdit()
                dto = QDateEdit()
                for d in (dfrom, dto):
                    d.setCalendarPopup(True)
                    d.setDisplayFormat("yyyy-MM-dd")
                    d.setDate(QDate.currentDate())
                cur = self.current_filters.get(str(fid), {})
                sfrom = str(cur.get("from", "") or "")
                sto = str(cur.get("to", "") or "")
                if sfrom or sto:
                    chk.setChecked(True)
                if sfrom:
                    qd = QDate.fromString(sfrom, "yyyy-MM-dd")
                    if qd.isValid():
                        dfrom.setDate(qd)
                if sto:
                    qd = QDate.fromString(sto, "yyyy-MM-dd")
                    if qd.isValid():
                        dto.setDate(qd)
                h.addWidget(chk)
                h.addWidget(QLabel("desde"))
                h.addWidget(dfrom, 1)
                h.addWidget(QLabel("hasta"))
                h.addWidget(dto, 1)
                self._filter_widgets[fid] = ("date_range", (chk, dfrom, dto))
                filt_form.addRow(label + ":", row)

            elif ftype == "bool":
                cb = QComboBox()
                cb.addItem("(cualquiera)", None)
                cb.addItem("Sí", 1)
                cb.addItem("No", 0)
                cur = self.current_filters.get(str(fid), {}).get("is", None)
                idx = cb.findData(cur)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                self._filter_widgets[fid] = ("bool_is", cb)
                filt_form.addRow(label + ":", cb)

            elif ftype == "relation":
                opts = parse_field_options_json(f)
                target_tid = int(opts.get("target_table_id", 0) or 0)
                display_fid = int(opts.get("display_field_id", 0) or 0)
                cb = QComboBox()
                cb.addItem("(cualquiera)", 0)
                if target_tid > 0:
                    for rid, lbl in self.repo.list_relation_options(target_tid, display_fid, limit=2000):
                        cb.addItem(lbl, rid)
                cur = int(self.current_filters.get(str(fid), {}).get("is", 0) or 0)
                idx = cb.findData(cur)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                self._filter_widgets[fid] = ("relation_is", cb)
                filt_form.addRow(label + ":", cb)

        root.addWidget(filt_box)

        btns = QHBoxLayout()
        root.addLayout(btns)
        btns.addStretch(1)
        b_clear = QPushButton("Limpiar")
        b_cancel = QPushButton("Cancelar")
        b_ok = QPushButton("Aplicar")
        b_ok.setDefault(True)
        btns.addWidget(b_clear)
        btns.addWidget(b_cancel)
        btns.addWidget(b_ok)
        b_clear.clicked.connect(self._clear)
        b_cancel.clicked.connect(self.reject)
        b_ok.clicked.connect(self.accept)

    def _clear(self):
        self.sort_field.setCurrentIndex(0)
        self.sort_dir.setCurrentIndex(0)
        for fid, (kind, w) in self._filter_widgets.items():
            if kind == "text_contains":
                w.setText("")
            elif kind in ("select_equals", "bool_is", "relation_is"):
                w.setCurrentIndex(0)
            elif kind == "number_range":
                chk, mn, mx = w
                chk.setChecked(False)
                mn.setValue(0.0)
                mx.setValue(0.0)
            elif kind == "date_range":
                chk, dfrom, dto = w
                chk.setChecked(False)
                dfrom.setDate(QDate.currentDate())
                dto.setDate(QDate.currentDate())

    def get_view_state(self) -> dict:
        filters: Dict[str, dict] = {}
        for f in self.fields:
            fid = int(f["id"])
            kind, w = self._filter_widgets.get(fid, (None, None))
            if not kind:
                continue

            if kind == "text_contains":
                s = w.text().strip()
                if s:
                    filters[str(fid)] = {"contains": s}

            elif kind == "select_equals":
                v = w.currentData()
                if v:
                    filters[str(fid)] = {"equals": str(v)}

            elif kind == "number_range":
                chk, mn, mx = w
                if chk.isChecked():
                    vmin = float(mn.value())
                    vmax = float(mx.value())
                    d = {}
                    if vmin != 0.0 and vmax == 0.0:
                        d["min"] = vmin
                    elif vmax != 0.0 and vmin == 0.0:
                        d["max"] = vmax
                    else:
                        d["min"] = vmin
                        d["max"] = vmax
                    filters[str(fid)] = d

            elif kind == "date_range":
                chk, dfrom, dto = w
                if chk.isChecked():
                    filters[str(fid)] = {
                        "from": dfrom.date().toString("yyyy-MM-dd"),
                        "to": dto.date().toString("yyyy-MM-dd"),
                    }

            elif kind == "bool_is":
                v = w.currentData()
                if v in (0, 1):
                    filters[str(fid)] = {"is": int(v)}

            elif kind == "relation_is":
                v = int(w.currentData() or 0)
                if v > 0:
                    filters[str(fid)] = {"is": v}

        sort_field_id = self.sort_field.currentData()
        sort_dir = self.sort_dir.currentData() or "DESC"
        return {"filters": filters, "sort_field_id": sort_field_id, "sort_dir": sort_dir}


    # Accesos rápidos (compat)
    def get_filters(self) -> Dict[str, dict]:
        return (self.get_view_state() or {}).get("filters", {})

    def get_sort(self) -> Tuple[Optional[int], str]:
        st = self.get_view_state() or {}
        return st.get("sort_field_id"), (st.get("sort_dir") or "DESC")
# -------------------- record dialog --------------------
class RecordDialog(QDialog):
    def __init__(self, parent=None, repo: Optional[MetaRepository] = None, table_id: int = 0, fields=None, values: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Registro"))
        self.repo = repo
        self.table_id = int(table_id)
        self._fields = fields or []
        self._widgets: Dict[int, Any] = {}
        self._values = values or {}

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        for f in self._fields:
            fid = int(f["id"])
            ftype = f["ftype"]
            label = f["name"]

            if ftype == "text":
                w = QLineEdit(str(self._values.get(fid, "")) if self._values else "")

            elif ftype == "select":
                opts = parse_field_options_json(f).get("options", [])
                w = QComboBox()
                w.addItem("", "")
                for o in opts:
                    w.addItem(o, o)
                cur = str(self._values.get(fid, "") or "")
                idx = w.findData(cur)
                if idx >= 0:
                    w.setCurrentIndex(idx)

            elif ftype == "relation":
                opts = parse_field_options_json(f)
                target_tid = int(opts.get("target_table_id", 0) or 0)
                display_fid = int(opts.get("display_field_id", 0) or 0)
                cb = QComboBox()
                cb.addItem("", 0)
                if self.repo and target_tid > 0:
                    for rid, lbl in self.repo.list_relation_options(target_tid, display_fid, limit=2000):
                        cb.addItem(lbl, rid)
                cur = int(self._values.get(fid, 0) or 0)
                idx = cb.findData(cur)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                w = cb

            elif ftype == "number":
                w = QDoubleSpinBox()
                w.setRange(-1e12, 1e12)
                w.setDecimals(2)
                if fid in self._values and self._values[fid] not in (None, ""):
                    try:
                        w.setValue(float(self._values[fid]))
                    except Exception:
                        pass

            elif ftype == "date":
                w = QDateEdit()
                w.setCalendarPopup(True)
                w.setDisplayFormat("yyyy-MM-dd")
                s = str(self._values.get(fid, "") or "")
                if s:
                    d = QDate.fromString(s, "yyyy-MM-dd")
                    if d.isValid():
                        w.setDate(d)
                else:
                    w.setDate(QDate.currentDate())

            elif ftype == "bool":
                w = QCheckBox("Sí")
                w.setChecked(bool(int(self._values.get(fid, 0) or 0)))

            elif ftype == "file":
                line = QLineEdit(str(self._values.get(fid, "") or ""))
                line.setReadOnly(True)
                b = QPushButton("Elegir…")
                def pick():
                    path, _ = QFileDialog.getOpenFileName(self, tr("Seleccionar archivo"), "", "Todos (*.*)")
                    if path:
                        line.setText(path)
                b.clicked.connect(pick)
                row = QHBoxLayout()
                row.addWidget(line, 1)
                row.addWidget(b)
                wrap = QWidget()
                wrap.setLayout(row)
                w = wrap
                self._widgets[fid] = line
                form.addRow(label + ":", w)
                continue

            
            elif ftype == "image":
                line = QLineEdit(str(self._values.get(fid, "") or ""))
                line.setReadOnly(True)
                b = QPushButton(tr("Elegir imagen…"))
                preview = QLabel()
                preview.setFixedSize(64, 64)
                preview.setAlignment(Qt.AlignCenter)
                preview.setStyleSheet("border: 1px solid rgba(255,255,255,0.15); border-radius: 8px;")

                def _set_preview(p: str):
                    try:
                        if not p:
                            preview.clear()
                            return
                        # If stored name (vault), show it too:
                        cand = Path(p)
                        if not cand.exists():
                            cand = Path(VAULT_DIR) / p
                        if cand.exists():
                            pm = QPixmap(str(cand))
                            if not pm.isNull():
                                preview.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                            else:
                                preview.setText("IMG")
                        else:
                            preview.setText("IMG")
                    except Exception:
                        preview.setText("IMG")

                _set_preview(line.text().strip())

                def pick_img():
                    path, _ = QFileDialog.getOpenFileName(
                        self,
                        tr("Seleccionar imagen"),
                        "",
                        tr("Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Todos (*.*)")
                    )
                    if path:
                        line.setText(path)
                        _set_preview(path)

                b.clicked.connect(pick_img)
                row = QHBoxLayout()
                row.addWidget(line, 1)
                row.addWidget(b)
                row.addWidget(preview)
                wrap = QWidget()
                wrap.setLayout(row)
                w = wrap
                self._widgets[fid] = line
                form.addRow(label + ":", w)
                continue
            elif ftype == "path":
                line = QLineEdit(str(self._values.get(fid, "") or ""))
                line.setReadOnly(True)
                b = QPushButton(tr("Elegir carpeta…"))
                def pick_dir():
                    path = QFileDialog.getExistingDirectory(self, tr("Seleccionar carpeta"))
                    if path:
                        line.setText(path)
                b.clicked.connect(pick_dir)
                row = QHBoxLayout()
                row.addWidget(line, 1)
                row.addWidget(b)
                wrap = QWidget()
                wrap.setLayout(row)
                w = wrap
                self._widgets[fid] = line
                form.addRow(label + ":", w)
                continue

            else:
                w = QLineEdit(str(self._values.get(fid, "")) if self._values else "")

            self._widgets[fid] = w
            form.addRow(label + ":", w)

        btns = QHBoxLayout()
        root.addLayout(btns)
        btns.addStretch(1)
        b_cancel = QPushButton("Cancelar")
        b_ok = QPushButton("Guardar")
        b_ok.setDefault(True)
        btns.addWidget(b_cancel)
        btns.addWidget(b_ok)
        b_cancel.clicked.connect(self.reject)
        b_ok.clicked.connect(self.accept)

    def get_values(self) -> Dict[int, Any]:
        out: Dict[int, Any] = {}
        for f in self._fields:
            fid = int(f["id"])
            ftype = f["ftype"]
            w = self._widgets[fid]
            if ftype == "text":
                out[fid] = w.text().strip()
            elif ftype == "select":
                out[fid] = str(w.currentData() or "")
            elif ftype == "relation":
                out[fid] = int(w.currentData() or 0)
            elif ftype == "number":
                out[fid] = float(w.value())
            elif ftype == "date":
                out[fid] = w.date().toString("yyyy-MM-dd")
            elif ftype == "bool":
                out[fid] = 1 if w.isChecked() else 0
            elif ftype == "file":
                out[fid] = normalize_attachment_input(w.text().strip())
            elif ftype == "path":
                out[fid] = w.text().strip()
            else:
                out[fid] = getattr(w, "text", lambda: "")().strip()
        return out

    # Compat: old API
    def get_data(self):
        return self.get_values()

# -------------------- Fields panel --------------------
class FieldsPanel(QWidget):
    """
    Panel lateral para:
      - ocultar/mostrar columnas (checkbox)
      - reordenar campos (drag & drop)
      - acciones: añadir/renombrar/borrar
    """
    ROLE_FIELD_ID = Qt.UserRole + 10

    def __init__(self, repo: MetaRepository, table_id: int, on_change_cb, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.table_id = int(table_id)
        self.on_change_cb = on_change_cb  # callback cuando cambien prefs u orden

        root = QVBoxLayout(self)
        head = QHBoxLayout()
        root.addLayout(head)

        lbl = QLabel("Campos")
        lbl.setStyleSheet("font-weight: 700;")
        head.addWidget(lbl)
        head.addStretch(1)

        self.btn_add = QToolButton()
        self.btn_add.setToolTip("Añadir campo")
        self.btn_add.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        self.btn_add.clicked.connect(self.add_field)
        head.addWidget(self.btn_add)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        root.addWidget(self.list, 1)

        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.customContextMenuRequested.connect(self._context_menu)

        hint = QLabel("Tip: arrastra para reordenar · marca para ocultar/mostrar")
        hint.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        root.addWidget(hint)

        self.reload()

    def reload(self):
        prefs = self.repo.get_table_prefs(self.table_id) or {}
        hidden = set(int(x) for x in prefs.get("hidden_field_ids", []) if int(x) > 0)

        self.list.blockSignals(True)
        self.list.clear()

        fields = self.repo.list_fields(self.table_id, active_only=True)
        for f in fields:
            fid = int(f["id"])
            txt = f"{f['name']}  ·  {TYPE_LABELS.get(f['ftype'], f['ftype'])}"
            it = QListWidgetItem(txt)
            it.setData(self.ROLE_FIELD_ID, fid)
            it.setToolTip(f"ID campo: {fid}\nTipo: {f['ftype']}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setCheckState(Qt.Unchecked if fid in hidden else Qt.Checked)  # checked = visible
            self.list.addItem(it)

        self.list.blockSignals(False)

    def _current_order_field_ids(self) -> List[int]:
        ids = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            ids.append(int(it.data(self.ROLE_FIELD_ID)))
        return ids

    def _save_prefs(self):
        prefs = self.repo.get_table_prefs(self.table_id) or {}
        hidden = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            fid = int(it.data(self.ROLE_FIELD_ID))
            if it.checkState() != Qt.Checked:
                hidden.append(fid)
        prefs["hidden_field_ids"] = hidden
        # field_order is implicit in meta_fields.position; keep optional copy for debugging
        prefs["field_order"] = self._current_order_field_ids()
        self.repo.save_table_prefs(self.table_id, prefs)

    def _on_rows_moved(self, *args):
        # reorder fields in DB to persist
        ids = self._current_order_field_ids()
        self.repo.reorder_fields(self.table_id, ids)
        self._save_prefs()
        self.on_change_cb()

    def _on_item_changed(self, item: QListWidgetItem):
        self._save_prefs()
        self.on_change_cb()

    def _context_menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        fid = int(it.data(self.ROLE_FIELD_ID))
        name = it.text().split("·")[0].strip()

        menu = QMenu(self)
        act_ren = QAction(tr("Renombrar…"), self)
        act_del = QAction(tr("Borrar campo…"), self)
        menu.addAction(act_ren)
        menu.addAction(act_del)

        def do_ren():
            new_name, ok = QInputDialog.getText(self, tr("Renombrar campo"), tr("Nuevo nombre:"), text=name)
            if not ok:
                return
            try:
                self.repo.rename_field(fid, new_name)
            except Exception as e:
                QMessageBox.critical(self, tr("Error"), str(e))
                return
            self.reload()
            self.on_change_cb()

        def do_del():
            res = QMessageBox.question(
                self, tr("Borrar campo"),
                f"¿Borrar el campo '{name}'?\n\nEl dato no se elimina físicamente (solo se desactiva).",
                QMessageBox.Yes | QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return
            try:
                self.repo.deactivate_field(fid)
            except Exception as e:
                QMessageBox.critical(self, tr("Error"), str(e))
                return
            self.reload()
            self.on_change_cb()

        act_ren.triggered.connect(do_ren)
        act_del.triggered.connect(do_del)

        menu.exec(self.list.mapToGlobal(pos))

    def add_field(self):
        dlg = AddFieldDialog(self.repo, self.table_id, self)
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.get_data()
        try:
            self.repo.add_field(self.table_id, d["name"], d["ftype"], required=d["required"], options=d["options"])
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.reload()
        self.on_change_cb()

# -------------------- Table View (inline edit + saved views + undo/redo) --------------------

class FieldDelegate(QStyledItemDelegate):
    """
    Delegate por columna según tipo de campo para edición inline.
    """
    def __init__(self, view: "TableView", field: dict, parent=None):
        super().__init__(parent)
        self.view = view
        self.field = field or {}

    def createEditor(self, parent, option, index):
        ftype = self.field.get("ftype")
        if ftype == "image":
            return None
        if ftype == "file":
            return None
        if ftype == "path":
            return None
        if ftype == "number":
            ed = QDoubleSpinBox(parent)
            ed.setDecimals(6)
            ed.setMinimum(-1e18)
            ed.setMaximum(1e18)
            ed.setAccelerated(True)
            return ed
        if ftype == "date":
            ed = QDateEdit(parent)
            ed.setCalendarPopup(True)
            ed.setDisplayFormat("yyyy-MM-dd")
            ed.setSpecialValueText("")  # allow empty
            return ed
        if ftype == "bool":
            ed = QComboBox(parent)
            ed.addItem("—", None)
            ed.addItem("Sí", 1)
            ed.addItem("No", 0)
            return ed
        if ftype == "select":
            ed = QComboBox(parent)
            ed.addItem("—", "")
            for opt in (self.field.get("options") or {}).get("choices", []):
                ed.addItem(str(opt), str(opt))
            return ed
        if ftype == "relation":
            ed = QComboBox(parent)
            ed.addItem("—", None)
            rel_table_id = (self.field.get("options") or {}).get("table_id")
            if rel_table_id:
                for rid, label in self.view.get_relation_options(int(rel_table_id)):
                    ed.addItem(label, int(rid))
            return ed
        # text, file, path
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        item = self.view.table.item(index.row(), index.column())
        raw = item.data(self.view.ROLE_RAW) if item else None
        ftype = self.field.get("ftype")

        if isinstance(editor, QDoubleSpinBox):
            try:
                editor.setValue(float(raw) if raw not in (None, "") else 0.0)
            except Exception:
                editor.setValue(0.0)
            return

        if isinstance(editor, QDateEdit):
            if raw:
                try:
                    d = QDate.fromString(str(raw), "yyyy-MM-dd")
                    if d.isValid():
                        editor.setDate(d)
                except Exception:
                    pass
            return

        if isinstance(editor, QComboBox):
            # match by data first
            for i in range(editor.count()):
                if editor.itemData(i) == raw:
                    editor.setCurrentIndex(i)
                    return
            # fallback: match by text
            if raw is not None:
                s = str(raw)
                for i in range(editor.count()):
                    if editor.itemText(i) == s:
                        editor.setCurrentIndex(i)
                        return
            editor.setCurrentIndex(0)
            return

        # QLineEdit
        editor.setText("" if raw is None else str(raw))

    def setModelData(self, editor, model, index):
        ftype = self.field.get("ftype")
        new_raw = None

        if isinstance(editor, QDoubleSpinBox):
            new_raw = float(editor.value())
        elif isinstance(editor, QDateEdit):
            d = editor.date()
            new_raw = d.toString("yyyy-MM-dd") if d and d.isValid() else ""
        elif isinstance(editor, QComboBox):
            new_raw = editor.currentData()
            if ftype == "select":
                # select uses string choices
                new_raw = "" if new_raw is None else str(new_raw)
        else:
            new_raw = editor.text().strip()

        display = self.view.apply_inline_edit(index.row(), index.column(), new_raw)

        # Set visible text in table
        model.setData(index, display)


class TableView(QWidget):
    ROLE_RECORD_ID = Qt.UserRole + 1
    ROLE_RAW = Qt.UserRole + 2

    def __init__(self, repo: MetaRepository, table_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.table_id = int(table_id)

        # view state
        self.view_filters: Dict[str, dict] = {}
        self.sort_field_id = None
        self.sort_dir = "DESC"
        self._view_dirty = False
        self._view_loading = False
        self.current_view_id: Optional[int] = None

        # undo stack
        self._undo: List[dict] = []
        self._undo_idx: int = 0
        self._in_undo_redo = False

        self._relation_cache: Dict[int, List[Tuple[int, str]]] = {}
        self.fields: List[dict] = []
        self.visible_fields: List[dict] = []
        self.hidden_field_ids: set[int] = set()

        # layout: splitter (grid + fields panel)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # toolbar row
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 8, 8, 8)
        bar.setSpacing(8)

        st = self.style()

        # Views selector
        bar.addWidget(QLabel(tr("Vista:")))
        self.cmb_views = QComboBox()
        self.cmb_views.setMinimumWidth(180)
        self.cmb_views.currentIndexChanged.connect(self._on_view_changed)
        bar.addWidget(self.cmb_views)

        self.btn_views = QToolButton()
        self.btn_views.setIcon(st.standardIcon(QStyle.SP_TitleBarMenuButton))
        self.btn_views.setPopupMode(QToolButton.InstantPopup)
        self.menu_views = QMenu(self)
        self.act_view_save = QAction(st.standardIcon(QStyle.SP_DialogSaveButton), tr("Guardar vista"), self)
        self.act_view_save_as = QAction(st.standardIcon(QStyle.SP_DialogSaveButton), tr("Guardar como…"), self)
        self.act_view_rename = QAction(tr("Renombrar…"), self)
        self.act_view_delete = QAction(st.standardIcon(QStyle.SP_TrashIcon), tr("Borrar…"), self)
        self.menu_views.addAction(self.act_view_save)
        self.menu_views.addAction(self.act_view_save_as)
        self.menu_views.addSeparator()
        self.menu_views.addAction(self.act_view_rename)
        self.menu_views.addAction(self.act_view_delete)
        self.btn_views.setMenu(self.menu_views)
        bar.addWidget(self.btn_views)

        self.act_view_save.triggered.connect(self.save_current_view)
        self.act_view_save_as.triggered.connect(self.save_view_as)
        self.act_view_rename.triggered.connect(self.rename_current_view)
        self.act_view_delete.triggered.connect(self.delete_current_view)

        bar.addSpacing(12)

        # View options (filters / sort)
        self.act_view = QAction(st.standardIcon(QStyle.SP_FileDialogDetailedView), tr("Filtros/Orden"), self)
        btn_view = QToolButton()
        btn_view.setDefaultAction(self.act_view)
        bar.addWidget(btn_view)

        self.act_clear = QAction(st.standardIcon(QStyle.SP_DialogResetButton), tr("Limpiar"), self)
        btn_clear = QToolButton()
        btn_clear.setDefaultAction(self.act_clear)
        bar.addWidget(btn_clear)

        # Undo/Redo
        self.act_undo = QAction(st.standardIcon(QStyle.SP_ArrowBack), tr("Deshacer"), self)
        self.act_redo = QAction(st.standardIcon(QStyle.SP_ArrowForward), tr("Rehacer"), self)
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        btn_undo = QToolButton()
        btn_undo.setDefaultAction(self.act_undo)
        btn_redo = QToolButton()
        btn_redo.setDefaultAction(self.act_redo)
        bar.addWidget(btn_undo)
        bar.addWidget(btn_redo)

        self.act_undo.triggered.connect(self.undo)
        self.act_redo.triggered.connect(self.redo)

        bar.addStretch(1)

        # Search
        bar.addWidget(QLabel(tr("Buscar:")))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Texto o ID…"))
        self.search.textChanged.connect(self._on_search_changed)
        bar.addWidget(self.search, 1)

        # Columns panel toggle
        self.act_cols = QAction(st.standardIcon(QStyle.SP_ComputerIcon), tr("Campos"), self)
        self.act_cols.setCheckable(True)
        self.act_cols.setChecked(True)
        btn_cols = QToolButton()
        btn_cols.setDefaultAction(self.act_cols)
        bar.addWidget(btn_cols)

        # Export
        self.act_pdf = QAction(st.standardIcon(QStyle.SP_DialogSaveButton), tr("PDF"), self)
        self.act_csv = QAction(st.standardIcon(QStyle.SP_DialogSaveButton), tr("CSV"), self)
        btn_pdf = QToolButton(); btn_pdf.setDefaultAction(self.act_pdf)
        btn_csv = QToolButton(); btn_csv.setDefaultAction(self.act_csv)
        bar.addWidget(btn_pdf); bar.addWidget(btn_csv)

        # Records
        self.act_add = QAction(st.standardIcon(QStyle.SP_FileDialogNewFolder), tr("Añadir"), self)
        self.act_edit = QAction(st.standardIcon(QStyle.SP_FileDialogContentsView), tr("Editar"), self)
        self.act_del = QAction(st.standardIcon(QStyle.SP_TrashIcon), tr("Borrar"), self)
        btn_add = QToolButton(); btn_add.setDefaultAction(self.act_add)
        btn_edit = QToolButton(); btn_edit.setDefaultAction(self.act_edit)
        btn_del = QToolButton(); btn_del.setDefaultAction(self.act_del)
        bar.addWidget(btn_add); bar.addWidget(btn_edit); bar.addWidget(btn_del)

        root.addLayout(bar)

        # splitter: table + fields
        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Horizontal)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Inline edit:
        # - no edit on double click by default (we handle double click ourselves so file/path can "open")
        self.table.setEditTriggers(QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)

        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)

        self.splitter.addWidget(self.table)

        self.fields_panel = FieldsPanel(self.repo, self.table_id, self.on_fields_changed, self)
        self.splitter.addWidget(self.fields_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

        root.addWidget(self.splitter, 1)

        # wire actions
        self.act_view.triggered.connect(self.open_view_dialog)
        self.act_clear.triggered.connect(self.clear_view)
        self.act_cols.triggered.connect(self.toggle_fields)
        self.act_pdf.triggered.connect(self.export_pdf)
        self.act_csv.triggered.connect(self.export_csv)
        self.act_add.triggered.connect(self.add_record)
        self.act_edit.triggered.connect(self.edit_record)
        self.act_del.triggered.connect(self.delete_record)

        self.act_edit.setEnabled(False)
        self.act_del.setEnabled(False)
        self.table.itemSelectionChanged.connect(self._on_sel_changed)

        self.reload()
        self.load_views()
        self._update_undo_actions()

    # ---------- helpers ----------
    def _update_undo_actions(self):
        self.act_undo.setEnabled(self._undo_idx > 0)
        self.act_redo.setEnabled(self._undo_idx < len(self._undo))

    def push_cmd(self, label: str, undo_fn, redo_fn):
        if self._in_undo_redo:
            return
        self._undo = self._undo[:self._undo_idx]
        self._undo.append({"label": label, "undo": undo_fn, "redo": redo_fn})
        self._undo_idx += 1
        self._update_undo_actions()

    def undo(self):
        if self._undo_idx <= 0:
            return
        self._in_undo_redo = True
        try:
            self._undo_idx -= 1
            cmd = self._undo[self._undo_idx]
            cmd["undo"]()
        finally:
            self._in_undo_redo = False
        self._update_undo_actions()
        self.refresh()

    def redo(self):
        if self._undo_idx >= len(self._undo):
            return
        self._in_undo_redo = True
        try:
            cmd = self._undo[self._undo_idx]
            cmd["redo"]()
            self._undo_idx += 1
        finally:
            self._in_undo_redo = False
        self._update_undo_actions()
        self.refresh()

    def _mark_view_dirty(self, dirty=True):
        if self._view_loading:
            return
        self._view_dirty = bool(dirty)
        idx = self.cmb_views.currentIndex()
        if idx < 0:
            return
        base = self.cmb_views.itemData(idx, Qt.UserRole + 1234) or self.cmb_views.itemText(idx).replace(" *", "")
        self.cmb_views.setItemData(idx, base, Qt.UserRole + 1234)
        self.cmb_views.setItemText(idx, base + (" *" if self._view_dirty else ""))

    def get_relation_options(self, rel_table_id: int) -> List[Tuple[int, str]]:
        rel_table_id = int(rel_table_id)
        if rel_table_id in self._relation_cache:
            return self._relation_cache[rel_table_id]
        opts = []
        try:
            rows = self.repo.list_records(rel_table_id, query="", limit=5000, filters=None, sort_field_id=None, sort_dir="ASC")
            # label: first text/select field if exists, else ID
            rel_fields = [dict(r) for r in self.repo.list_fields(rel_table_id)]
            label_fid = None
            for f in rel_fields:
                if f["ftype"] in ("text", "select", "path"):
                    label_fid = int(f["id"]); break
            for r in rows:
                rid = int(r["id"])
                label = str(r[f"f_{label_fid}"]) if (label_fid and f"f_{label_fid}" in r.keys()) else str(rid)
                label = label if label else str(rid)
                opts.append((rid, label))
        except Exception:
            pass
        self._relation_cache[rel_table_id] = opts
        return opts

    def _relation_label(self, field: dict, rid: Any) -> str:
        if rid in (None, "", 0):
            return ""
        try:
            rid = int(rid)
        except Exception:
            return str(rid)
        rel_table_id = (field.get("options") or {}).get("table_id")
        if not rel_table_id:
            return str(rid)
        for _rid, label in self.get_relation_options(int(rel_table_id)):
            if int(_rid) == rid:
                return label
        return str(rid)

    def _bool_label(self, v: Any) -> str:
        if v in (1, True, "1", "true", "True", "sí", "si", "Sí"):
            return "Sí"
        if v in (0, False, "0", "false", "False", "no", "No"):
            return "No"
        return ""

    def _display_for(self, field: dict, raw: Any) -> str:
        ftype = field.get("ftype")
        if raw is None:
            return ""
        if ftype == "bool":
            return self._bool_label(raw)
        if ftype == "relation":
            return self._relation_label(field, raw)
        return str(raw)

    # ---------- views ----------
    def current_view_state(self) -> dict:
        prefs = self.repo.get_table_prefs(self.table_id) or {}
        hidden = prefs.get("hidden_field_ids", [])
        # column widths
        widths = {}
        try:
            widths["id"] = int(self.table.columnWidth(0))
        except Exception:
            pass
        for i, f in enumerate(self.visible_fields, start=1):
            try:
                widths[str(int(f["id"]))] = int(self.table.columnWidth(i))
            except Exception:
                pass
        return {
            "filters": self.view_filters or {},
            "sort_field_id": self.sort_field_id,
            "sort_dir": self.sort_dir or "DESC",
            "search": self.search.text().strip(),
            "hidden_field_ids": hidden,
            "fields_panel": bool(self.act_cols.isChecked()),
            "col_widths": widths,
        }

    def apply_view_state(self, state: dict):
        state = state or {}
        self._view_loading = True
        try:
            # filters/sort
            self.view_filters = state.get("filters") or {}
            self.sort_field_id = state.get("sort_field_id")
            self.sort_dir = state.get("sort_dir") or "DESC"

            # search
            self.search.blockSignals(True)
            self.search.setText(state.get("search") or "")
            self.search.blockSignals(False)

            # fields panel visibility
            want_cols = bool(state.get("fields_panel", True))
            self.act_cols.blockSignals(True)
            self.act_cols.setChecked(want_cols)
            self.act_cols.blockSignals(False)
            self.fields_panel.setVisible(want_cols)

            # hidden fields -> table prefs (keeps panel in sync)
            prefs = self.repo.get_table_prefs(self.table_id) or {}
            prefs["hidden_field_ids"] = list(state.get("hidden_field_ids") or [])
            self.repo.save_table_prefs(self.table_id, prefs)
            self.fields_panel.reload()

            self.refresh()

            # restore widths
            widths = state.get("col_widths") or {}
            try:
                if "id" in widths:
                    self.table.setColumnWidth(0, int(widths["id"]))
            except Exception:
                pass
            for i, f in enumerate(self.visible_fields, start=1):
                fid = str(int(f["id"]))
                if fid in widths:
                    try:
                        self.table.setColumnWidth(i, int(widths[fid]))
                    except Exception:
                        pass
        finally:
            self._view_loading = False
        self._mark_view_dirty(False)

    def load_views(self):
        self.cmb_views.blockSignals(True)
        self.cmb_views.clear()

        views = self.repo.list_views(self.table_id)
        if not views:
            # create default
            vid = self.repo.create_view(self.table_id, "Principal", self.current_view_state())
            views = self.repo.list_views(self.table_id)

        for v in views:
            vid = int(v["id"])
            name = str(v["name"])
            self.cmb_views.addItem(name, vid)

        self.cmb_views.blockSignals(False)

        # select last view if present
        prefs = self.repo.get_table_prefs(self.table_id) or {}
        last_vid = prefs.get("last_view_id")
        idx = -1
        if last_vid is not None:
            for i in range(self.cmb_views.count()):
                if self.cmb_views.itemData(i) == last_vid:
                    idx = i
                    break
        if idx < 0:
            idx = 0 if self.cmb_views.count() else -1

        if idx >= 0:
            self.cmb_views.setCurrentIndex(idx)
            self.current_view_id = int(self.cmb_views.itemData(idx))
            # apply view content
            row = self.repo.get_view(self.current_view_id)
            try:
                state = json.loads(row["view_json"] or "{}")
            except Exception:
                state = {}
            self.apply_view_state(state)

    def _on_view_changed(self, i: int):
        if self._view_loading:
            return
        if i < 0:
            return

        # If dirty, ask to save
        if self._view_dirty and self.current_view_id is not None:
            res = QMessageBox.question(self, tr("Vista"), "Tienes cambios sin guardar en la vista actual.\n\n¿Guardar ahora?",
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if res == QMessageBox.Cancel:
                # revert selection
                self._view_loading = True
                try:
                    # find index of current_view_id
                    for j in range(self.cmb_views.count()):
                        if self.cmb_views.itemData(j) == self.current_view_id:
                            self.cmb_views.setCurrentIndex(j)
                            break
                finally:
                    self._view_loading = False
                return
            if res == QMessageBox.Yes:
                self.save_current_view()

        self.current_view_id = int(self.cmb_views.itemData(i))
        prefs = self.repo.get_table_prefs(self.table_id) or {}
        prefs["last_view_id"] = self.current_view_id
        self.repo.save_table_prefs(self.table_id, prefs)

        row = self.repo.get_view(self.current_view_id)
        try:
            state = json.loads(row["view_json"] or "{}")
        except Exception:
            state = {}
        self.apply_view_state(state)

    def save_current_view(self):
        if self.current_view_id is None:
            return
        try:
            self.repo.update_view(self.current_view_id, view=self.current_view_state())
            self._mark_view_dirty(False)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    def save_view_as(self):
        name, ok = QInputDialog.getText(self, tr("Guardar vista como…"), tr("Nombre de la nueva vista:"))
        if not ok:
            return
        try:
            vid = self.repo.create_view(self.table_id, name, self.current_view_state())
            self.load_views()
            # select new
            for i in range(self.cmb_views.count()):
                if self.cmb_views.itemData(i) == vid:
                    self.cmb_views.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    def rename_current_view(self):
        if self.current_view_id is None:
            return
        cur_name = self.cmb_views.currentText().replace(" *", "")
        name, ok = QInputDialog.getText(self, tr("Renombrar vista"), tr("Nuevo nombre:"), text=cur_name)
        if not ok:
            return
        try:
            self.repo.update_view(self.current_view_id, name=name)
            self.load_views()
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    def delete_current_view(self):
        if self.current_view_id is None:
            return
        if self.cmb_views.count() <= 1:
            QMessageBox.information(self, tr("Vista"), "No puedes borrar la última vista.")
            return
        res = QMessageBox.question(self, tr("Borrar vista"), "¿Seguro que quieres borrar esta vista?",
                                   QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes:
            return
        try:
            self.repo.delete_view(self.current_view_id)
            self.current_view_id = None
            self.load_views()
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    # ---------- data / schema ----------
    def reload(self):
        self.fields = [dict(r) for r in self.repo.list_fields(self.table_id)]
        prefs = self.repo.get_table_prefs(self.table_id) or {}
        self.hidden_field_ids = set(int(x) for x in prefs.get("hidden_field_ids", []))
        self.visible_fields = [f for f in self.fields if int(f["id"]) not in self.hidden_field_ids]
        self.refresh()

    def refresh(self):
        records = self.repo.list_records(
            self.table_id,
            query=self.search.text().strip(),
            limit=5000,
            filters=self.view_filters,
            sort_field_id=self.sort_field_id,
            sort_dir=self.sort_dir,
        )

        cols = 1 + len(self.visible_fields)
        self.table.blockSignals(True)
        self.table.clear()
        self.table.setColumnCount(cols)
        headers = ["ID"] + [f["name"] for f in self.visible_fields]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(records))

        # delegates per column
        for i, f in enumerate(self.visible_fields, start=1):
            self.table.setItemDelegateForColumn(i, FieldDelegate(self, f, self.table))

        for r_idx, r in enumerate(records):
            rid = int(r["id"])
            # id item
            it_id = QTableWidgetItem(str(rid))
            it_id.setData(self.ROLE_RECORD_ID, rid)
            it_id.setFlags(it_id.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r_idx, 0, it_id)

            for c_idx, f in enumerate(self.visible_fields, start=1):
                fid = int(f["id"])
                raw = r[f"f_{fid}"] if f"f_{fid}" in r.keys() else None
                disp = self._display_for(f, raw)
                it = QTableWidgetItem(disp)
                it.setData(self.ROLE_RECORD_ID, rid)
                it.setData(self.ROLE_RAW, raw)

                # Non-inline-editable types
                if f["ftype"] in ("file", "path", "image"):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setFlags(it.flags() | Qt.ItemIsEditable)

                # Thumbnail for images
                if f["ftype"] == "image" and raw:
                    try:
                        p = Path(VAULT_DIR) / str(raw)
                        if p.exists():
                            pm = QPixmap(str(p))
                            if not pm.isNull():
                                it.setIcon(QIcon(pm.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                                it.setText(Path(str(raw)).name)
                    except Exception:
                        pass

                self.table.setItem(r_idx, c_idx, it)

        self.table.blockSignals(False)

    # ---------- inline edit ----------
    def apply_inline_edit(self, row: int, col: int, new_raw: Any) -> str:
        # col 0 = ID
        if col <= 0 or col > len(self.visible_fields):
            return ""
        item = self.table.item(row, col)
        if not item:
            return ""
        rid = int(item.data(self.ROLE_RECORD_ID) or 0)
        field = self.visible_fields[col - 1]
        fid = int(field["id"])
        old_raw = item.data(self.ROLE_RAW)

        # normalize
        ftype = field.get("ftype")
        if ftype == "relation":
            if new_raw in ("", 0):
                new_raw = None
            if new_raw is not None:
                try:
                    new_raw = int(new_raw)
                except Exception:
                    pass
        elif ftype == "bool":
            if new_raw is None:
                new_raw = None
            else:
                new_raw = 1 if new_raw in (1, True, "1") else 0
        elif ftype == "number":
            if new_raw in ("", None):
                new_raw = None
        elif ftype == "date":
            new_raw = "" if new_raw is None else str(new_raw)

        if old_raw == new_raw:
            return self._display_for(field, old_raw)

        # apply update
        def do(v):
            self.repo.update_record(self.table_id, rid, {fid: v})

        do(new_raw)

        # push undo
        def undo_fn():
            do(old_raw)

        def redo_fn():
            do(new_raw)

        self.push_cmd(f"Editar {field['name']}", undo_fn, redo_fn)

        # update cached raw in item
        item.setData(self.ROLE_RAW, new_raw)
        return self._display_for(field, new_raw)

    # ---------- action handlers ----------
    def on_item_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        row = item.row()
        col = item.column()

        if col == 0:
            # open edit dialog
            self.edit_record()
            return

        field = self.visible_fields[col - 1]
        ftype = field.get("ftype")
        raw = item.data(self.ROLE_RAW)
        if ftype == "image" and raw:
            try:
                p = Path(VAULT_DIR) / str(raw)
                if p.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
                    return
            except Exception:
                pass

        if ftype == "file" and raw:
            try:
                p = Path(VAULT_DIR) / str(raw)
                if p.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
                    return
            except Exception:
                pass
        if ftype == "path" and raw:
            try:
                p = Path(str(raw))
                if p.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
                    return
            except Exception:
                pass

        # otherwise begin inline edit
        self.table.editItem(item)

    def _on_sel_changed(self):
        has = len(self.table.selectedItems()) > 0
        self.act_edit.setEnabled(has)
        self.act_del.setEnabled(has)

    def _selected_record_id(self) -> Optional[int]:
        sel = self.table.selectedItems()
        if not sel:
            return None
        row = sel[0].row()
        it = self.table.item(row, 0)
        if not it:
            return None
        try:
            return int(it.text())
        except Exception:
            return None

    def open_view_dialog(self):
        dlg = ViewOptionsDialog(
            self.repo,
            self.table_id,
            self.fields,
            current_filters=self.view_filters,
            current_sort={"field_id": self.sort_field_id, "dir": self.sort_dir},
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        self.view_filters = dlg.get_filters()
        self.sort_field_id, self.sort_dir = dlg.get_sort()
        self._mark_view_dirty(True)
        self.refresh()

    def clear_view(self):
        self.view_filters = {}
        self.sort_field_id = None
        self.sort_dir = "DESC"
        self.search.setText("")
        self._mark_view_dirty(True)
        self.refresh()

    def toggle_fields(self):
        vis = self.act_cols.isChecked()
        self.fields_panel.setVisible(vis)
        self._mark_view_dirty(True)

    def on_fields_changed(self):
        # prefs updated by FieldsPanel
        self.reload()
        self._mark_view_dirty(True)

    def _on_search_changed(self, _):
        self._mark_view_dirty(True)
        self.refresh()

    # ---------- record CRUD with undo ----------
    def add_record(self):
        dlg = RecordDialog(parent=self, repo=self.repo, table_id=self.table_id, fields=self.fields, values={})
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.get_data()
        try:
            rid = self.repo.add_record(self.table_id, data)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return

        # Undo = delete; Redo = insert with same id
        def undo_fn():
            self.repo.delete_record(self.table_id, rid)

        def redo_fn():
            self.repo.add_record_with_id(self.table_id, rid, data)

        self.push_cmd("Añadir registro", undo_fn, redo_fn)
        self.refresh()

    def edit_record(self):
        rid = self._selected_record_id()
        if rid is None:
            return
        # snapshot
        old_row = self.repo.get_record_by_id(self.table_id, rid)
        old_vals = {}
        for f in self.fields:
            fid = int(f["id"])
            old_vals[fid] = old_row[f"f_{fid}"] if f"f_{fid}" in old_row.keys() else None

        dlg = RecordDialog(parent=self, repo=self.repo, table_id=self.table_id, fields=self.fields, values=old_vals)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.get_data()
        try:
            self.repo.update_record(self.table_id, rid, data)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return

        def undo_fn():
            self.repo.update_record(self.table_id, rid, old_vals)

        def redo_fn():
            self.repo.update_record(self.table_id, rid, data)

        self.push_cmd("Editar registro", undo_fn, redo_fn)
        self.refresh()

    def delete_record(self):
        rid = self._selected_record_id()
        if rid is None:
            return
        res = QMessageBox.question(self, tr("Borrar"), f"¿Borrar el registro {rid}?", QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes:
            return

        old_row = self.repo.get_record_by_id(self.table_id, rid)
        old_vals = {}
        for f in self.fields:
            fid = int(f["id"])
            old_vals[fid] = old_row[f"f_{fid}"] if f"f_{fid}" in old_row.keys() else None
        created_at = old_row["created_at"] if "created_at" in old_row.keys() else None
        updated_at = old_row["updated_at"] if "updated_at" in old_row.keys() else None

        try:
            self.repo.delete_record(self.table_id, rid)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return

        def undo_fn():
            self.repo.add_record_with_id(self.table_id, rid, old_vals, created_at=created_at, updated_at=updated_at)

        def redo_fn():
            self.repo.delete_record(self.table_id, rid)

        self.push_cmd("Borrar registro", undo_fn, redo_fn)
        self.refresh()

    # ---------- export ----------
    # ---------- export helpers ----------
    def _current_rows_for_export(self):
        return self.repo.list_records(
            self.table_id,
            query=self.search.text().strip(),
            limit=5000,
            filters=self.view_filters,
            sort_field_id=self.sort_field_id,
            sort_dir=self.sort_dir,
        )

    def export_csv(self):
        out_path, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV"), "", "CSV (*.csv)")
        if not out_path:
            return

        rows = self._current_rows_for_export()
        headers = ["id"] + [f["name"] for f in self.visible_fields]

        try:
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for r in rows:
                    line = [int(r["id"])]
                    for field in self.visible_fields:
                        fid = int(field["id"])
                        col = f"f_{fid}"
                        raw = r[col] if col in r.keys() else ""
                        if field["ftype"] == "relation":
                            raw = self._relation_label(field, raw)
                        elif field["ftype"] == "bool":
                            raw = self._bool_label(raw)
                        line.append("" if raw is None else raw)
                    w.writerow(line)
            QMessageBox.information(self, tr("Exportado"), f"CSV guardado en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    def export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            QMessageBox.critical(
                self,
                tr("Falta dependencia"),
                "No está instalado reportlab.\n\nInstala con:\n  pip install reportlab",
            )
            return

        out_path, _ = QFileDialog.getSaveFileName(self, tr("Exportar PDF"), "", "PDF (*.pdf)")
        if not out_path:
            return

        rows = self._current_rows_for_export()

        try:
            styles = getSampleStyleSheet()
            doc = SimpleDocTemplate(
                out_path,
                pagesize=landscape(A4),
                leftMargin=18, rightMargin=18, topMargin=18, bottomMargin=18,
            )
            story = []

            title = self.repo.get_table(self.table_id)["name"]
            story.append(Paragraph(f"Tabla: {title}", styles["Title"]))
            story.append(Spacer(1, 8))

            headers = ["ID"] + [f["name"] for f in self.visible_fields]
            data = [headers]

            for r in rows[:5000]:
                line = [str(int(r["id"]))]
                for field in self.visible_fields:
                    fid = int(field["id"])
                    col = f"f_{fid}"
                    raw = r[col] if col in r.keys() else ""
                    if field["ftype"] == "relation":
                        raw = self._relation_label(field, raw)
                    elif field["ftype"] == "bool":
                        raw = self._bool_label(raw)
                    line.append("" if raw is None else str(raw))
                data.append(line)

            tbl = Table(data, repeatRows=1)

            # Light theme for PDF (avoid dark UI bleed)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ]))

            story.append(tbl)
            doc.build(story)
            QMessageBox.information(self, tr("Exportado"), f"PDF guardado en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))



    # ---------- context menu ----------
    def context_menu(self, pos):
        it = self.table.itemAt(pos)
        if not it:
            return
        row = it.row()
        rid_item = self.table.item(row, 0)
        rid = int(rid_item.text()) if rid_item else None

        menu = QMenu(self)
        menu.addAction(self.act_add)
        if rid is not None:
            menu.addAction(self.act_edit)
            menu.addAction(self.act_del)
        menu.addSeparator()

        # quick open for file/path
        col = it.column()
        if col > 0:
            field = self.visible_fields[col - 1]
            ftype = field.get("ftype")
            raw = it.data(self.ROLE_RAW)
            if ftype == "image" and raw:
                act_open = QAction(tr("Abrir imagen"), self)
                act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(VAULT_DIR)/str(raw)))))
                menu.addAction(act_open)
            if ftype == "path" and raw:
                act_open = QAction(tr("Abrir carpeta"), self)
                act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(raw))))
                menu.addAction(act_open)
            if ftype == "file" and raw:
                act_open = QAction(tr("Abrir archivo"), self)
                act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(VAULT_DIR)/str(raw)))))
                menu.addAction(act_open)

        menu.exec(self.table.mapToGlobal(pos))

class MainWindow(QMainWindow):
    ROLE_KIND = Qt.UserRole
    ROLE_ID = Qt.UserRole + 1

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(1360, 780)

        self.repo = MetaRepository()

        # Top toolbar (grouped actions)
        self.topbar = QToolBar(tr("Acciones"))
        self.topbar.setMovable(False)
        self.topbar.setIconSize(QSize(18, 18))
        self.addToolBar(self.topbar)

        st = self.style()
        self.act_new_project = QAction(st.standardIcon(QStyle.SP_DirIcon), tr("Proyecto"), self)
        self.act_new_subproject = QAction(st.standardIcon(QStyle.SP_DirOpenIcon), tr("Subproyecto"), self)
        self.act_new_subproject.setToolTip(tr("Nuevo subproyecto en el proyecto seleccionado"))
        self.act_new_project.setToolTip(tr("Nuevo proyecto"))
        self.act_new_table = QAction(st.standardIcon(QStyle.SP_FileIcon), tr("Tabla"), self)
        self.act_new_table.setToolTip(tr("Nueva tabla"))
        self.act_rename_table = QAction(st.standardIcon(QStyle.SP_FileDialogContentsView), tr("Renombrar"), self)
        self.act_move_table = QAction(st.standardIcon(QStyle.SP_ArrowRight), tr("Mover"), self)
        self.act_delete_table = QAction(st.standardIcon(QStyle.SP_TrashIcon), "Borrar tabla", self)

        self.topbar.addAction(self.act_new_project)
        self.topbar.addAction(self.act_new_subproject)
        self.topbar.addSeparator()
        self.topbar.addAction(self.act_new_table)
        self.topbar.addAction(self.act_rename_table)
        self.topbar.addAction(self.act_move_table)
        self.topbar.addAction(self.act_delete_table)
        self.topbar.addSeparator()
        self.act_export_db = QAction(st.standardIcon(QStyle.SP_DialogSaveButton), tr("Exportar DB"), self)
        self.act_import_db = QAction(st.standardIcon(QStyle.SP_DialogOpenButton), tr("Cargar DB"), self)
        self.topbar.addAction(self.act_export_db)
        self.topbar.addAction(self.act_import_db)

        self.act_new_project.triggered.connect(self.create_project)
        self.act_new_subproject.triggered.connect(self.create_subproject_from_selection)
        self.act_new_table.triggered.connect(self.create_table)
        self.act_rename_table.triggered.connect(self.rename_selected_table)
        self.act_move_table.triggered.connect(self.move_selected_table_prompt)
        self.act_delete_table.triggered.connect(self.delete_selected_table)
        self.act_export_db.triggered.connect(self.export_database)
        self.act_import_db.triggered.connect(self.import_database)

        self._build_menu_bar()

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter()
        splitter.setHandleWidth(6)
        root.addWidget(splitter, 1)

        # Left panel: projects + tables (tree)
        left = QWidget()
        lroot = QVBoxLayout(left)
        splitter.addWidget(left)

        # Tree header
        head = QHBoxLayout()
        lroot.addLayout(head)
        title = QLabel(tr("Proyectos"))
        title.setStyleSheet("font-weight: 700;")
        head.addWidget(title)
        head.addStretch(1)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        lroot.addWidget(self.tree, 1)

        # Right panel: table view
        self.right = QWidget()
        self.right_layout = QVBoxLayout(self.right)
        splitter.addWidget(self.right)
        splitter.setStretchFactor(1, 1)

        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree.customContextMenuRequested.connect(self.tree_context_menu)

        self.reload_tree()
        self.on_tree_selection_changed()

    def closeEvent(self, e):
        self.repo.close()
        super().closeEvent(e)

    
    # ---------- menu bar / i18n ----------
    def _build_menu_bar(self):
        """
        Create a classic text-based menu bar (File / Edit / View / Help).
        All actions already exist as QAction objects in the UI.
        """
        mb = self.menuBar()
        mb.clear()

        # File
        m_file = mb.addMenu(tr("Archivo"))
        m_file.addAction(self.act_export_db)
        m_file.addAction(self.act_import_db)
        m_file.addSeparator()
        act_exit = QAction(tr("Salir"), self)
        act_exit.setShortcut(QKeySequence.Quit)
        act_exit.triggered.connect(self.close)
        m_file.addAction(act_exit)

        # Edit (table-level undo/redo)
        m_edit = mb.addMenu(tr("Editar"))
        self.act_menu_undo = QAction(tr("Deshacer"), self)
        self.act_menu_redo = QAction(tr("Rehacer"), self)
        self.act_menu_undo.setShortcut(QKeySequence.Undo)
        self.act_menu_redo.setShortcut(QKeySequence.Redo)
        self.act_menu_undo.triggered.connect(lambda: self._with_table(lambda v: v.undo()))
        self.act_menu_redo.triggered.connect(lambda: self._with_table(lambda v: v.redo()))
        m_edit.addAction(self.act_menu_undo)
        m_edit.addAction(self.act_menu_redo)

        # View (table-level)
        m_view = mb.addMenu(tr("Ver"))
        act_toggle_fields = QAction(tr("Campos"), self)
        act_toggle_fields.triggered.connect(lambda: self._with_table(lambda v: v.act_cols.trigger()))
        m_view.addAction(act_toggle_fields)
        act_filters = QAction(tr("Filtros/Orden"), self)
        act_filters.triggered.connect(lambda: self._with_table(lambda v: v.open_view_dialog()))
        m_view.addAction(act_filters)
        act_clear = QAction(tr("Limpiar"), self)
        act_clear.triggered.connect(lambda: self._with_table(lambda v: v.clear_view()))
        m_view.addAction(act_clear)

        m_view.addSeparator()
        act_view_save = QAction(tr("Guardar vista"), self)
        act_view_save.triggered.connect(lambda: self._with_table(lambda v: v.save_current_view()))
        m_view.addAction(act_view_save)
        act_view_save_as = QAction(tr("Guardar como…"), self)
        act_view_save_as.triggered.connect(lambda: self._with_table(lambda v: v.save_view_as()))
        m_view.addAction(act_view_save_as)
        act_view_rename = QAction(tr("Renombrar…"), self)
        act_view_rename.triggered.connect(lambda: self._with_table(lambda v: v.rename_current_view()))
        m_view.addAction(act_view_rename)
        act_view_delete = QAction(tr("Borrar…"), self)
        act_view_delete.triggered.connect(lambda: self._with_table(lambda v: v.delete_current_view()))
        m_view.addAction(act_view_delete)

        # Project / Table
        m_proj = mb.addMenu(tr("Proyecto"))
        m_proj.addAction(self.act_new_project)
        m_proj.addAction(self.act_new_subproject)

        m_table = mb.addMenu(tr("Tabla"))
        m_table.addAction(self.act_new_table)
        m_table.addAction(self.act_rename_table)
        m_table.addAction(self.act_move_table)
        m_table.addAction(self.act_delete_table)

        # Records (table-level)
        m_rec = mb.addMenu(tr("Registros"))
        act_add = QAction(tr("Añadir"), self)
        act_add.setShortcut(QKeySequence.New)
        act_add.triggered.connect(lambda: self._with_table(lambda v: v.add_record()))
        m_rec.addAction(act_add)
        act_edit = QAction(tr("Editar"), self)
        act_edit.triggered.connect(lambda: self._with_table(lambda v: v.edit_record()))
        m_rec.addAction(act_edit)
        act_del = QAction(tr("Borrar"), self)
        act_del.setShortcut(QKeySequence.Delete)
        act_del.triggered.connect(lambda: self._with_table(lambda v: v.delete_record()))
        m_rec.addAction(act_del)
        m_rec.addSeparator()
        act_csv = QAction(tr("CSV"), self)
        act_csv.triggered.connect(lambda: self._with_table(lambda v: v.export_csv()))
        act_pdf = QAction(tr("PDF"), self)
        act_pdf.triggered.connect(lambda: self._with_table(lambda v: v.export_pdf()))
        m_rec.addAction(act_csv)
        m_rec.addAction(act_pdf)

        # Language
        m_lang = mb.addMenu(tr("Idioma"))
        act_es = QAction(tr("Español"), self)
        act_en = QAction(tr("English"), self)
        act_es.setCheckable(True)
        act_en.setCheckable(True)
        cur = get_language()
        act_es.setChecked(cur == "es")
        act_en.setChecked(cur == "en")
        act_es.triggered.connect(lambda: self.change_language("es"))
        act_en.triggered.connect(lambda: self.change_language("en"))
        m_lang.addAction(act_es)
        m_lang.addAction(act_en)

        # Help
        m_help = mb.addMenu(tr("Ayuda"))
        act_about = QAction(tr("Acerca de"), self)
        act_about.triggered.connect(self.show_about)
        m_help.addAction(act_about)

        self._update_menu_enabled()

    def _update_menu_enabled(self):
        """Enable/disable table-scoped actions based on selection."""
        has_table = getattr(self, "current_table_view", None) is not None
        for a in getattr(self, "act_menu_undo", None), getattr(self, "act_menu_redo", None):
            if a:
                a.setEnabled(has_table)

    def _with_table(self, fn):
        """Run a callable against the currently open TableView (if any)."""
        v = getattr(self, "current_table_view", None)
        if v is None:
            return
        try:
            fn(v)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    def show_about(self):
        """
        Show application information.
        """
        info = "\n".join([
            f"{APP_NAME}",
            f"{tr('Versión')}: {APP_VERSION}",
            f"{tr('Fecha')}: {APP_RELEASE_DATE}",
            f"{tr('Autor')}: {APP_AUTHOR}",
        ])
        QMessageBox.information(self, tr("Acerca de"), info)

    def change_language(self, lang: str):
        """Persist language and restart the main window so all UI strings are rebuilt."""
        cur = get_language()
        lang = "en" if (lang or "").lower().startswith("en") else "es"
        if cur == lang:
            return
        set_language(lang)

        # Preserve current table selection if possible
        kind, tid = self.selected_node()
        keep_tid = tid if kind == "table" else None

        # Create the new window first, then close the current one
        w = MainWindow()
        w.show()
        if keep_tid is not None:
            try:
                w.reload_tree(keep_table_id=int(keep_tid))
                w.on_tree_selection_changed()
            except Exception:
                pass
        self.close()

# ---------- helpers ----------
    def clear_right(self):
        self.current_table_view = None
        try:
            self._update_menu_enabled()
        except Exception:
            pass

        while self.right_layout.count():
            w = self.right_layout.takeAt(0).widget()
            if w:
                w.setParent(None)

    def selected_node(self) -> Tuple[Optional[str], Optional[int]]:
        items = self.tree.selectedItems()
        if not items:
            return None, None
        it = items[0]
        kind = it.data(0, self.ROLE_KIND)
        nid = it.data(0, self.ROLE_ID)
        return kind, (int(nid) if nid is not None else None)

    def current_project_id_for_new_table(self) -> Optional[int]:
        kind, nid = self.selected_node()
        if kind == "project":
            return nid
        if kind == "table":
            parent = self.tree.selectedItems()[0].parent()
            if parent and parent.data(0, self.ROLE_KIND) == "project":
                pid = parent.data(0, self.ROLE_ID)
                return int(pid) if pid is not None else None
        return None

    def current_table_id(self) -> Optional[int]:
        kind, nid = self.selected_node()
        return nid if kind == "table" else None

    # ---------- tree reload ----------
    def reload_tree(self, keep_table_id: Optional[int] = None):
        self.tree.clear()

        projects = [dict(r) for r in self.repo.list_projects()]
        tables = [dict(r) for r in self.repo.list_tables()]

        proj_items: Dict[Optional[int], QTreeWidgetItem] = {}

        # "Sin proyecto"
        unassigned = QTreeWidgetItem([tr("Sin proyecto")])
        unassigned.setData(0, self.ROLE_KIND, "project")
        unassigned.setData(0, self.ROLE_ID, None)
        unassigned.setIcon(0, color_icon("#64748B"))
        self.tree.addTopLevelItem(unassigned)
        proj_items[None] = unassigned

        # Create all project items (not attached yet)
        for p in projects:
            pid = int(p["id"])
            name = p["name"]
            color = (p.get("color") or "#4C9AFF").strip()
            item = QTreeWidgetItem([name])
            item.setData(0, self.ROLE_KIND, "project")
            item.setData(0, self.ROLE_ID, pid)
            item.setIcon(0, color_icon(color))
            proj_items[pid] = item

        # Attach projects according to parent_id
        # Sort by name for stable UX
        projects_sorted = sorted(projects, key=lambda x: str(x.get("name") or "").lower())
        for p in projects_sorted:
            pid = int(p["id"])
            parent_id = p.get("parent_id")
            if parent_id is None:
                self.tree.addTopLevelItem(proj_items[pid])
            else:
                parent_item = proj_items.get(int(parent_id))
                if parent_item is None:
                    self.tree.addTopLevelItem(proj_items[pid])
                else:
                    parent_item.addChild(proj_items[pid])

        # Add tables under project items
        for t in sorted(tables, key=lambda x: str(x.get("name") or "").lower()):
            tid = int(t["id"])
            name = t["name"]
            pid = int(t["project_id"]) if t.get("project_id") is not None else None
            parent = proj_items.get(pid, unassigned)
            child = QTreeWidgetItem([name])
            child.setData(0, self.ROLE_KIND, "table")
            child.setData(0, self.ROLE_ID, tid)
            child.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))
            parent.addChild(child)

        self.tree.expandAll()

        if keep_table_id is not None:
            it = self._find_table_item(keep_table_id)
            if it:
                self.tree.setCurrentItem(it)


        if keep_table_id is not None:
            it = self._find_table_item(keep_table_id)
            if it:
                self.tree.setCurrentItem(it)

    def _find_table_item(self, table_id: int) -> Optional[QTreeWidgetItem]:
        def walk(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            if item.data(0, self.ROLE_KIND) == "table" and int(item.data(0, self.ROLE_ID)) == int(table_id):
                return item
            for i in range(item.childCount()):
                r = walk(item.child(i))
                if r:
                    return r
            return None

        for i in range(self.tree.topLevelItemCount()):
            r = walk(self.tree.topLevelItem(i))
            if r:
                return r
        return None

    # ---------- selection ----------
    def on_tree_selection_changed(self):
        tid = self.current_table_id()
        self.clear_right()
        if tid is None:
            lbl = QLabel(tr("Selecciona una tabla para ver sus registros."))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #9CA3AF; font-size: 14px;")
            self.right_layout.addWidget(lbl, 1)
            return
        view = TableView(self.repo, tid, parent=self.right)
        self.current_table_view = view
        try:
            self._update_menu_enabled()
        except Exception:
            pass
        self.right_layout.addWidget(view, 1)

    # ---------- project actions ----------
    def create_project(self):
        name, ok = QInputDialog.getText(self, tr("Nuevo proyecto"), tr("Nombre del proyecto:"))
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        col = QColorDialog.getColor(QColor("#4C9AFF"), self, tr("Color del proyecto"))
        color_hex = col.name() if col.isValid() else "#4C9AFF"
        try:
            self.repo.create_project(name, color_hex)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.reload_tree()

    def rename_project(self, project_id: int):
        projects = {int(p["id"]): p for p in self.repo.list_projects()}
        cur = projects.get(int(project_id))
        if not cur:
            return
        name, ok = QInputDialog.getText(self, tr("Renombrar proyecto"), tr("Nuevo nombre:"), text=str(cur["name"]))
        if not ok:
            return
        try:
            self.repo.update_project(project_id, name=name)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.reload_tree()


    def _current_project_id(self) -> Optional[int]:
        """
        Devuelve el project_id seleccionado (si está seleccionada una tabla,
        devuelve el proyecto padre).
        """
        item = self.tree.currentItem()
        if not item:
            return None
        kind = item.data(0, self.ROLE_KIND)
        nid = item.data(0, self.ROLE_ID)
        if kind == "project":
            return int(nid) if nid is not None else None

        # table -> parent project
        parent = item.parent()
        while parent:
            if parent.data(0, self.ROLE_KIND) == "project":
                pid = parent.data(0, self.ROLE_ID)
                return int(pid) if pid is not None else None
            parent = parent.parent()
        return None

    def _project_path(self, pid: int) -> str:
        """
        Devuelve el path del proyecto: Padre / Hijo / ...
        """
        projects = {int(p["id"]): dict(p) for p in self.repo.list_projects()}
        parts = []
        cur = projects.get(int(pid))
        seen = set()
        while cur and int(cur["id"]) not in seen:
            seen.add(int(cur["id"]))
            parts.append(str(cur.get("name") or ""))
            parent_id = cur.get("parent_id")
            cur = projects.get(int(parent_id)) if parent_id is not None else None
        parts = [p for p in reversed(parts) if p]
        return " / ".join(parts)

    def create_subproject_from_selection(self):
        pid = self._current_project_id()
        if pid is None:
            QMessageBox.information(self, tr("Subproyecto"), tr("Selecciona un proyecto (no 'Sin proyecto') para crear un subproyecto."))
            return
        self.create_subproject(pid)

    def create_subproject(self, parent_project_id: int):
        name, ok = QInputDialog.getText(self, tr("Nuevo subproyecto"), tr("Nombre del subproyecto:"))
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        try:
            parent_color = "#4C9AFF"
            for p in self.repo.list_projects():
                if int(p["id"]) == int(parent_project_id):
                    parent_color = str(p["color"] or "#4C9AFF")
                    break
            self.repo.create_project(name, color=parent_color, parent_id=int(parent_project_id))
            self.reload_tree()
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))


    def set_project_color(self, project_id: int):
        projects = {int(p["id"]): p for p in self.repo.list_projects()}
        cur = projects.get(int(project_id))
        if not cur:
            return
        current_color = str(cur["color"] or "#4C9AFF")
        col = QColorDialog.getColor(QColor(current_color), self, tr("Color del proyecto"))
        if not col.isValid():
            return
        try:
            self.repo.update_project(project_id, color=col.name())
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.reload_tree()

    def delete_project(self, project_id: int):
        projects = {int(p["id"]): p for p in self.repo.list_projects()}
        cur = projects.get(int(project_id))
        if not cur:
            return
        res = QMessageBox.question(
            self, tr("Borrar proyecto"),
            f"¿Borrar el proyecto '{cur['name']}'?\n\nLas tablas se quedarán en 'Sin proyecto'.",
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return
        try:
            self.repo.delete_project(project_id)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.reload_tree()

    # ---------- table actions ----------
    def create_table(self):
        pid = self.current_project_id_for_new_table()
        name, ok = QInputDialog.getText(self, tr("Nueva tabla"), tr("Nombre de la tabla:"))
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        try:
            tid = self.repo.create_table(name, project_id=pid)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.reload_tree(keep_table_id=tid)
        self.on_tree_selection_changed()

    def rename_selected_table(self):
        tid = self.current_table_id()
        if tid is None:
            return
        cur_name = self.repo.get_table(tid)["name"]
        name, ok = QInputDialog.getText(self, tr("Renombrar tabla"), tr("Nuevo nombre:"), text=str(cur_name))
        if not ok:
            return
        try:
            self.repo.rename_table(tid, name)
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.reload_tree(keep_table_id=tid)

    def delete_selected_table(self):
        tid = self.current_table_id()
        if tid is None:
            return
        self._delete_table(tid)

    def _delete_table(self, table_id: int):
        t = self.repo.get_table(table_id)
        res = QMessageBox.question(
            self, tr("Borrar tabla"),
            f"¿Borrar la tabla '{t['name']}' y todos sus datos?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return
        self.repo.delete_table(table_id)
        self.reload_tree()
        self.on_tree_selection_changed()

    def move_selected_table_prompt(self):
        tid = self.current_table_id()
        if tid is None:
            return
        # choose project
        items = ["Sin proyecto"] + [str(p["name"]) for p in self.repo.list_projects()]
        choice, ok = QInputDialog.getItem(self, tr("Mover tabla"), tr("Proyecto destino:"), items, 0, False)
        if not ok:
            return
        if choice == "Sin proyecto":
            self.repo.set_table_project(tid, None)
        else:
            # find project id
            pid = None
            for p in self.repo.list_projects():
                if str(p["name"]) == choice:
                    pid = int(p["id"])
                    break
            self.repo.set_table_project(tid, pid)
        self.reload_tree(keep_table_id=tid)

    # ---------- DB backup / restore ----------
    def export_database(self):
        """
        Exporta:
          - .zip (recomendado): incluye la DB y la carpeta vault/
          - .sqlite3/.db: solo la DB
        """
        default_name = "baserow_lite_backup.zip"
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Exportar base de datos"),
            default_name,
            "Backup ZIP (*.zip);;SQLite DB (*.sqlite3 *.db)"
        )
        if not path:
            return

        path = str(path)
        is_zip = path.lower().endswith(".zip")
        if not is_zip and not (path.lower().endswith(".sqlite3") or path.lower().endswith(".db")):
            path += ".zip"
            is_zip = True

        try:
            # flush data
            try:
                self.repo.conn.commit()
            except Exception:
                pass

            db_src = Path(DB_PATH)
            vault_src = Path(VAULT_DIR)

            if is_zip:
                with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                    if db_src.exists():
                        z.write(str(db_src), arcname=str(Path("data") / db_src.name))
                    if vault_src.exists():
                        for fp in vault_src.rglob("*"):
                            if fp.is_file():
                                z.write(str(fp), arcname=str(Path("vault") / fp.relative_to(vault_src)))
                QMessageBox.information(self, tr("Exportado"), f"Backup guardado en:\n{path}")
            else:
                if not db_src.exists():
                    QMessageBox.warning(self, tr("Sin DB"), f"No se encontró la base de datos:\n{db_src}")
                    return
                shutil.copy2(str(db_src), path)
                QMessageBox.information(self, tr("Exportado"), f"DB guardada en:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    def import_database(self):
        """
        Carga:
          - .zip: restaura DB + vault (sobrescribe)
          - .sqlite3/.db: restaura solo DB (sobrescribe)
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Cargar base de datos"),
            "",
            "Backup ZIP (*.zip);;SQLite DB (*.sqlite3 *.db)"
        )
        if not path:
            return

        is_zip = str(path).lower().endswith(".zip")
        msg = tr("Esto sobrescribirá la base de datos actual")
        msg += (" y la carpeta vault" if is_zip else "")
        msg += ".\n\n¿Continuar?"
        res = QMessageBox.question(self, tr("Cargar base de datos"), msg, QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes:
            return

        db_dst = Path(DB_PATH)
        vault_dst = Path(VAULT_DIR)

        # Close repo before replacing DB file
        try:
            self.repo.close()
        except Exception:
            pass

        try:
            if is_zip:
                with tempfile.TemporaryDirectory() as td:
                    td = Path(td)
                    with zipfile.ZipFile(str(path), "r") as z:
                        z.extractall(td)

                    # locate DB inside extracted structure
                    cand = td / "data" / db_dst.name
                    if not cand.exists():
                        db_files = list(td.rglob("*.sqlite3")) + list(td.rglob("*.db"))
                        cand = db_files[0] if db_files else None
                    if not cand or not Path(cand).exists():
                        raise RuntimeError(tr("No se encontró una DB dentro del ZIP."))

                    db_dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(cand), str(db_dst))

                    # restore vault if present
                    src_vault = td / "vault"
                    if src_vault.exists():
                        if vault_dst.exists():
                            shutil.rmtree(vault_dst)
                        shutil.copytree(src_vault, vault_dst)
            else:
                db_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(db_dst))

            # reopen repo + refresh UI
            self.repo = MetaRepository()
            self.reload_tree()
            self.on_tree_selection_changed()
            QMessageBox.information(self, tr("Cargado"), "Base de datos cargada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            # try to keep app usable
            try:
                self.repo = MetaRepository()
                self.reload_tree()
                self.on_tree_selection_changed()
            except Exception:
                pass

    # ---------- tree context menu ----------
    def tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        kind = item.data(0, self.ROLE_KIND)
        nid = item.data(0, self.ROLE_ID)

        menu = QMenu(self)

        if kind == "project":
            pid = int(nid) if nid is not None else None
            act_new_table = QAction(tr("Nueva tabla…"), self)
            act_new_table.triggered.connect(self.create_table)
            menu.addAction(act_new_table)
            if pid is not None:
                act_new_sub = QAction(tr("Nuevo subproyecto…"), self)
                act_new_sub.triggered.connect(lambda: self.create_subproject(pid))
                menu.addAction(act_new_sub)
            menu.addSeparator()

            if pid is not None:
                act_ren = QAction(tr("Renombrar proyecto…"), self)
                act_col = QAction(tr("Cambiar color…"), self)
                act_del = QAction(tr("Borrar proyecto…"), self)
                act_ren.triggered.connect(lambda: self.rename_project(pid))
                act_col.triggered.connect(lambda: self.set_project_color(pid))
                act_del.triggered.connect(lambda: self.delete_project(pid))
                menu.addAction(act_ren)
                menu.addAction(act_col)
                menu.addSeparator()
                menu.addAction(act_del)

        elif kind == "table":
            tid = int(nid)
            act_open = QAction(tr("Abrir"), self)
            act_open.triggered.connect(lambda: self.tree.setCurrentItem(item))
            menu.addAction(act_open)

            act_ren = QAction(tr("Renombrar…"), self)
            act_ren.triggered.connect(self.rename_selected_table)
            menu.addAction(act_ren)

            sub = QMenu(tr("Mover a proyecto"), self)
            act_none = QAction(tr("Sin proyecto"), self)
            act_none.triggered.connect(lambda: (self.repo.set_table_project(tid, None), self.reload_tree(keep_table_id=tid)))
            sub.addAction(act_none)
            sub.addSeparator()
            for p in self.repo.list_projects():
                pid = int(p["id"])
                a = QAction(self._project_path(pid), self)
                a.triggered.connect(lambda checked=False, pid=pid: (self.repo.set_table_project(tid, pid), self.reload_tree(keep_table_id=tid)))
                sub.addAction(a)
            menu.addMenu(sub)

            menu.addSeparator()
            act_del = QAction(tr("Borrar tabla…"), self)
            act_del.triggered.connect(lambda: self._delete_table(tid))
            menu.addAction(act_del)

        menu.exec(self.tree.mapToGlobal(pos))


# ---------- DB backup / restore ----------
# Attach DB backup/restore methods robustly (even if class definition changes)

def run():
    app = QApplication([])
    app.setStyle("Fusion")
    app.setPalette(build_dark_palette())
    app.setStyleSheet(APP_STYLESHEET)
    w = MainWindow()
    w.show()
    app.exec()

if __name__ == "__main__":
    run()