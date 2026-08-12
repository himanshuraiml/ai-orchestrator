from dataclasses import dataclass


@dataclass(frozen=True)
class ToolProfile:
    id: str
    name: str

    capabilities: frozenset[str]

    requires_network: bool = False
    requires_filesystem: bool = False
    requires_approval: bool = False

    risk_level: str = "low"


@dataclass(frozen=True)
class RegisteredTool:
    id: str
    server: str
    name: str
    description: str
    input_schema: dict
    capabilities: frozenset[str]
    risk_level: str
