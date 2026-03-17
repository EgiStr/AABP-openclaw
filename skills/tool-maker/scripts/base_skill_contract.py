from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseSkill(ABC):
    name: str = "unnamed-skill"
    description: str = ""

    @abstractmethod
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def healthcheck(self) -> Dict[str, Any]:
        return {"ok": True, "skill": self.name}
