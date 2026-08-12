import pytest

from orchestrator.domain.tools import ToolProfile
from orchestrator.routing.policies import PolicyEngine
from orchestrator.tools.router import NoSuitableToolError, ToolRouter

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


def make_tool(
    id: str,
    *,
    capabilities: frozenset[str],
    requires_network: bool = False,
    requires_filesystem: bool = False,
    requires_approval: bool = False,
) -> ToolProfile:
    return ToolProfile(
        id=id,
        name=id,
        capabilities=capabilities,
        requires_network=requires_network,
        requires_filesystem=requires_filesystem,
        requires_approval=requires_approval,
    )


@pytest.fixture
def tools() -> list[ToolProfile]:
    return [
        make_tool("ocr", capabilities=frozenset({"pdf_to_text", "image_to_text"}), requires_filesystem=True),
        make_tool("browser", capabilities=frozenset({"web_search"}), requires_network=True),
        make_tool("git", capabilities=frozenset({"version_control"}), requires_approval=True),
    ]


@pytest.fixture
def policy_engine() -> PolicyEngine:
    return PolicyEngine(policies_config=POLICIES_CONFIG)


def test_capability_filter_selects_matching_tool(tools, policy_engine):
    router = ToolRouter(tools, policy_engine)

    selected = router.select({"pdf_to_text"})

    assert selected.id == "ocr"


def test_network_tool_rejected_under_default_policy(tools, policy_engine):
    router = ToolRouter(tools, policy_engine)

    with pytest.raises(NoSuitableToolError):
        router.select({"web_search"})


def test_network_tool_allowed_under_document_policy(tools, policy_engine):
    router = ToolRouter(tools, policy_engine)

    selected = router.select({"web_search"}, policy_name="document")

    assert selected.id == "browser"


def test_approval_required_tool_never_auto_selected(tools, policy_engine):
    router = ToolRouter(tools, policy_engine)

    with pytest.raises(NoSuitableToolError):
        router.select({"version_control"}, policy_name="document")


def test_no_suitable_tool_for_unknown_capability(tools, policy_engine):
    router = ToolRouter(tools, policy_engine)

    with pytest.raises(NoSuitableToolError):
        router.select({"vision"})
