"""Assistant de création de classe (workflow en 7 étapes)."""
from .subjects_catalog import (
    SectionDef,
    SECTIONS,
    PATTERNS,
    expand_pattern,
    get_section,
    list_sections,
)
from .class_wizard import (
    ClassDraft,
    run_wizard,
    create_workspaces_from_draft,
)

__all__ = [
    "SectionDef",
    "SECTIONS",
    "PATTERNS",
    "expand_pattern",
    "get_section",
    "list_sections",
    "ClassDraft",
    "run_wizard",
    "create_workspaces_from_draft",
]
