# BaseCT (0.1)

A lightweight, desktop-first mini database app built with **Python + PySide6**.
It lets you create projects and tables, define fields, and work with records in a spreadsheet-like UI.

**Author:** Jorge González  
**Version:** 0.1  
**Release date:** 2025-12-30

---

## Features

- **Projects + subprojects** (nested) and tables in a left tree.
- **Table grid**
  - Inline editing (double click)
  - Filters, sorting and search
  - Export current view to **CSV** and **PDF**
- **Saved views** per table (filters/sort/search/columns/panel width)
- **Undo / Redo** (Ctrl+Z / Ctrl+Y) for record edits (inline and dialogs)
- **Field types**
  - Text, Number, Date, Yes/No
  - Select
  - Relation (foreign key-style dropdown)
  - File and Path/Link
  - **Image** (stored in the vault + thumbnail in the table)
- **Database backup**
  - Export / Import the entire database as a `.zip` (includes the vault folder)

---

## Installation

Create an environment and install dependencies:

```bash
pip install PySide6
pip install reportlab   # optional, only needed for PDF export
```

---

## Run

From the `baserow_lite` folder:

```bash
python app.py
```

The app creates:

- `baserow_lite/data/baserow_lite.sqlite3` (database)
- `baserow_lite/vault/` (attachments: files/images)

---

## Import / Export (full database)

Use **File → Export DB** to create a `.zip` backup that contains:

- the SQLite database file
- the `vault/` folder with attachments

Use **File → Import DB** to restore from a previous backup.

---

## Language (Español / English)

Use **Language → Español / English**.
Changing language restarts the main window so all UI strings are rebuilt.

> Note: User-created content (table names, field names, record data) is never translated.

---

## Notes

- PDF export uses a **light** table theme (independent from the app dark UI) to ensure readability.
- Image fields behave like file fields:
  - In forms you choose an image file
  - The file is copied into the vault and referenced by name

---


