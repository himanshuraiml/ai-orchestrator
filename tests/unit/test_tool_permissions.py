from orchestrator.routing.policies import PolicyEngine
from orchestrator.tools.permissions import ToolPermissions
from orchestrator.tools.registry import ToolRegistry

POLICIES_CONFIG = {
    "policies": {
        "default": {
            "filesystem": {"read": True, "write": False},
            "network": {"enabled": False},
        },
        "document": {
            "filesystem": {"read": True, "write": True},
            "network": {"enabled": True},
        },
    }
}


def make_permissions() -> ToolPermissions:
    registry = ToolRegistry()
    policy_engine = PolicyEngine(policies_config=POLICIES_CONFIG)
    return ToolPermissions(registry, policy_engine)


def test_default_policy_excludes_network_tools():
    permissions = make_permissions()

    allowed_ids = {tool.id for tool in permissions.allowed_tools("default")}

    assert "browser" not in allowed_ids


def test_default_policy_excludes_approval_required_tools():
    permissions = make_permissions()

    allowed_ids = {tool.id for tool in permissions.allowed_tools("default")}

    assert "git" not in allowed_ids


def test_document_policy_allows_network_tools():
    permissions = make_permissions()

    allowed_ids = {tool.id for tool in permissions.allowed_tools("document")}

    assert "browser" in allowed_ids


def test_is_allowed_matches_allowed_tools():
    permissions = make_permissions()

    assert permissions.is_allowed("python", "default") is True
    assert permissions.is_allowed("browser", "default") is False


def test_is_allowed_false_for_unknown_tool():
    permissions = make_permissions()

    assert permissions.is_allowed("does_not_exist", "default") is False
