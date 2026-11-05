from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class GateOperator(Enum):
    EQ = "=="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="


class GateCondition(BaseModel):
    operator: GateOperator
    value: object


class Gate(BaseModel):
    name: str
    condition: GateCondition
    description: Optional[str] = ""


class GateResult(BaseModel):
    gate: str
    passed: bool
    evidence: str
    timestamp: Optional[str] = None