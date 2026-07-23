from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot


class DictListModel(QAbstractListModel):
    """Small, explicit Qt model for rows supplied by Beacon repositories."""

    def __init__(self, roles: Sequence[str]) -> None:
        super().__init__()
        self._rows: list[dict[str, Any]] = []
        self._role_ids = {
            Qt.ItemDataRole.UserRole + index: role
            for index, role in enumerate(roles, start=1)
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_ids.get(role)
        return self._rows[index.row()].get(name) if name else None

    def roleNames(self) -> dict[int, bytes]:
        return {
            role_id: name.encode("utf-8")
            for role_id, name in self._role_ids.items()
        }

    def replace(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = [dict(row) for row in rows]
        self.endResetModel()

    @Slot(int, result="QVariantMap")
    def get(self, index: int) -> dict[str, Any]:
        if 0 <= index < len(self._rows):
            return dict(self._rows[index])
        return {}

