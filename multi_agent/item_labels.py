"""Portuguese display labels for ms-inventory item conditions and states."""

ITEM_LABELS = {
    "NEW": "novo",
    "USED": "usado",
    "SEMI_DAMAGED": "semidanificado",
    "DAMAGED": "danificado",
    "DRAFT": "rascunho",
    "PENDING_APPROVAL": "aguardando aprovação",
    "REJECTED": "reprovado",
    "IN_STOCK": "em estoque",
    "IN_USE": "em uso",
    "IN_MAINTENANCE": "em manutenção",
    "AWAITING_EVALUATION": "aguardando avaliação",
    "DISPOSED": "descartado",
    "REMOVED": "removido",
}


def item_label(value: object) -> str:
    """Translate known enums while retaining free text and dropping invalid shapes."""
    if not isinstance(value, str):
        return ""
    return ITEM_LABELS.get(value.strip().upper(), value)
