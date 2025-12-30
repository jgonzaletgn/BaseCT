import shutil
from pathlib import Path
from uuid import uuid4
from typing import Optional

from constants import VAULT_DIR, FILES_DIR

def safe_copy_to_vault(src_path: Path) -> str:
    """
    Copia un archivo al vault y devuelve la ruta relativa (vault/..).
    """
    if not src_path.exists():
        return ""
    dst_name = f"{uuid4().hex}{src_path.suffix}"
    dst = FILES_DIR / dst_name
    shutil.copy2(src_path, dst)
    return str(dst.relative_to(VAULT_DIR)).replace("\\", "/")

def normalize_attachment_input(text: str) -> str:
    """
    Acepta: ruta absoluta existente, o ruta relativa al vault existente.
    Devuelve: ruta relativa al vault (o '' si no es válida).
    """
    s = (text or "").strip()
    if not s:
        return ""
    p = Path(s)
    if p.is_absolute() and p.exists():
        return safe_copy_to_vault(p)
    pv = VAULT_DIR / s
    if pv.exists():
        return s.replace("\\", "/")
    return ""
