"""
长期记忆 — 患者画像（1 条/人，永久存储）
"""

from __future__ import annotations

from harness.memory.persistence.repositories.profile_repo import ProfileRepo


class ProfileMemory:

    def __init__(self, repo: ProfileRepo, patient_id: str):
        self._repo = repo
        self.patient_id = patient_id

    def get(self) -> dict | None:
        return self._repo.get(self.patient_id)

    def save(self, data: dict) -> None:
        self._repo.save(self.patient_id, data)

    def update(self, updates: dict) -> None:
        self._repo.update(self.patient_id, updates)
