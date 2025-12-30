"""
Lightweight in-app i18n (Spanish / English).

- Spanish strings are the source of truth.
- When the UI language is set to English, known strings are translated through a dictionary.
- Unknown strings fall back to the original Spanish.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

SETTINGS_ORG = "BaserowLite"
SETTINGS_APP = "BaserowLite"
_KEY_LANG = "ui/language"


def get_language() -> str:
    """Return the current UI language ('es' or 'en')."""
    s = QSettings(SETTINGS_ORG, SETTINGS_APP)
    lang = (s.value(_KEY_LANG, "es") or "es").strip().lower()
    return "en" if lang.startswith("en") else "es"


def set_language(lang: str) -> None:
    """Persist the UI language ('es' or 'en')."""
    lang = (lang or "es").strip().lower()
    lang = "en" if lang.startswith("en") else "es"
    s = QSettings(SETTINGS_ORG, SETTINGS_APP)
    s.setValue(_KEY_LANG, lang)


# English translations keyed by the original Spanish UI strings.
_EN: dict[str, str] = {
    'Abrir': 'Open',
    'Abrir archivo': 'Open file',
    'Abrir carpeta': 'Open folder',
    'Abrir imagen': 'Open image',
    'Acciones': 'Actions',
    'Aceptar': 'OK',
    'Acerca de': 'About',
    'Archivo': 'File',
    'Autor': 'Author',
    'Aviso': 'Warning',
    'Ayuda': 'Help',
    'Añadir': 'Add',
    'Añadir campo': 'Add field',
    'Añadir registro': 'Add record',
    'Backup guardado en:\n{path}': 'Backup saved at:\n{path}',
    'Base de datos cargada correctamente.': 'Database imported successfully.',
    'Borrar': 'Delete',
    'Borrar campo': 'Delete field',
    'Borrar campo…': 'Delete field…',
    'Borrar proyecto': 'Delete project',
    'Borrar proyecto…': 'Delete project…',
    'Borrar registro': 'Delete record',
    'Borrar tabla': 'Delete table',
    'Borrar tabla…': 'Delete table…',
    'Borrar vista': 'Delete view',
    'Borrar…': 'Delete…',
    'Buscar:': 'Search:',
    'Cambiar color…': 'Change color…',
    'Campo:': 'Field:',
    'Campos': 'Fields',
    'Cancelar': 'Cancel',
    'Cargado': 'Loaded',
    'Cargar base de datos': 'Import database',
    'Cargar DB': 'Import DB',
    'Cerrar': 'Close',
    'Color del proyecto': 'Project color',
    'CSV': 'CSV',
    'CSV guardado en:\n{path}': 'CSV saved at:\n{path}',
    'Deshacer': 'Undo',
    'Dirección:': 'Path:',
    'Editar': 'Edit',
    'Editar registro': 'Edit record',
    'Elegir archivo…': 'Choose file…',
    'Elegir carpeta…': 'Choose folder…',
    'Elegir imagen…': 'Choose image…',
    'Error': 'Error',
    'Esto sobrescribirá la base de datos actual': 'This will overwrite the current database',
    'Exportado': 'Exported',
    'Exportar a CSV': 'Export to CSV',
    'Exportar a PDF': 'Export to PDF',
    'Exportar base de datos': 'Export database',
    'Exportar CSV': 'Export CSV',
    'Exportar DB': 'Export DB',
    'Exportar PDF': 'Export PDF',
    'Falta dependencia': 'Missing dependency',
    'Fecha': 'Date',
    'Filtros/Orden': 'Filters/Sort',
    'Guardar': 'Save',
    'Guardar como…': 'Save as…',
    'Guardar vista': 'Save view',
    'Guardar vista como…': 'Save view as…',
    'Idioma': 'Language',
    'Imagen': 'Image',
    'Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Todos (*.*)': 'Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All files (*.*)',
    'Información': 'Information',
    'Limpiar': 'Clear',
    'Mover': 'Move',
    'Mover a proyecto': 'Move to project',
    'Mover tabla': 'Move table',
    'No': 'No',
    'No está instalado reportlab.\n\nInstala con:\n  pip install reportlab': 'reportlab is not installed.\n\nInstall with:\n  pip install reportlab',
    'No puedes borrar la última vista.': 'You cannot delete the last view.',
    'No se encontró una DB dentro del ZIP.': 'No database file was found inside the ZIP.',
    'Nombre de la nueva vista:': 'New view name:',
    'Nombre de la tabla:': 'Table name:',
    'Nombre del campo': 'Field name',
    'Nombre del proyecto:': 'Project name:',
    'Nombre del subproyecto:': 'Subproject name:',
    'Nueva tabla': 'New table',
    'Nueva tabla…': 'New table…',
    'Nuevo': 'New',
    'Nuevo nombre:': 'New name:',
    'Nuevo proyecto': 'New project',
    'Nuevo subproyecto': 'New subproject',
    'Nuevo subproyecto en el proyecto seleccionado': 'New subproject in the selected project',
    'Nuevo subproyecto…': 'New subproject…',
    'Número': 'Number',
    'Opciones de relación': 'Relation options',
    'PDF': 'PDF',
    'PDF guardado en:\n{path}': 'PDF saved at:\n{path}',
    'Principal': 'Main',
    'Proyecto': 'Project',
    'Proyecto destino:': 'Target project:',
    'Proyectos': 'Projects',
    'Registro': 'Record',
    'Registros': 'Records',
    'Rehacer': 'Redo',
    'Relación': 'Relation',
    'Renombrar': 'Rename',
    'Renombrar campo': 'Rename field',
    'Renombrar proyecto': 'Rename project',
    'Renombrar proyecto…': 'Rename project…',
    'Renombrar tabla': 'Rename table',
    'Renombrar vista': 'Rename view',
    'Renombrar…': 'Rename…',
    'Ruta/Enlace': 'Path/Link',
    'Salir': 'Exit',
    "Selecciona un proyecto (no 'Sin proyecto') para crear un subproyecto.": "Select a project (not 'No project') to create a subproject.",
    'Selecciona una tabla para ver sus registros.': 'Select a table to view its records.',
    'Seleccionar archivo': 'Select file',
    'Seleccionar carpeta': 'Select folder',
    'Seleccionar imagen': 'Select image',
    'Select': 'Select',
    'Sin DB': 'No database',
    'Sin proyecto': 'No project',
    'Subproyecto': 'Subproject',
    'Sí': 'Yes',
    'Sí/No': 'Yes/No',
    'Tabla': 'Table',
    'Tabla destino:': 'Target table:',
    'Tabla: {title}': 'Table: {title}',
    'Texto': 'Text',
    'Texto o ID…': 'Text or ID…',
    'Tienes cambios sin guardar en la vista actual.\n\n¿Guardar ahora?': 'You have unsaved changes in the current view.\n\nSave now?',
    'Tipo': 'Type',
    'Una opción por línea (o separadas por coma).': 'One option per line (or comma-separated).',
    'Ver': 'View',
    'Versión': 'Version',
    'Vista': 'View',
    'Vista:': 'View:',
    'Vista: filtros y ordenación': 'View: filters and sorting',
    '¿Borrar el registro {rid}?': 'Delete record {rid}?',
    '¿Seguro que quieres borrar esta vista?': 'Are you sure you want to delete this view?',
}


def tr(text: str) -> str:
    """Translate a UI string to the current language."""
    if get_language() == "en":
        return _EN.get(text, text)
    return text
