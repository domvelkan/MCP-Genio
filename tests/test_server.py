import asyncio
import os

os.environ.setdefault("GENIO_MCP_TOKEN", "test-token-" + "x" * 40)
os.environ.setdefault("TELEGRAM_ALLOWED_CHAT_IDS", "12345")
import server


def test_service_name():
    assert server.APP_NAME == "MCP-Genio"


def test_unknown_workflow_not_allowed():
    assert "workflow-not-approved" not in server.N8N_ALLOWED_WORKFLOWS


def test_cockpit_help_command_returns_operator_commands():
    reply = asyncio.run(server.process_cockpit_command("99999", "/cockpit help"))
    assert "/cockpit status" in reply


def test_cockpit_requires_explicit_command():
    try:
        asyncio.run(server.process_cockpit_command("12345", "run something"))
    except ValueError:
        pass
    else:
        raise AssertionError("commands without /cockpit prefix should be rejected")


def test_provider_list_never_includes_secrets():
    providers = server.configured_providers()
    assert all(name in {"openrouter", "nvidia"} for name in providers)

def test_side_effecting_action_fails_closed_without_kernel_gateway():
    try:
        asyncio.run(server.authorize_action("n8n.workflow:demo", "12345", True))
    except RuntimeError as exc:
        assert "KERNEL_GATEWAY_URL" in str(exc) or "KERNEL_GATEWAY_TOKEN" in str(exc)
    else:
        raise AssertionError("execution must fail closed when Kernel is not configured")


def test_empty_workflow_list_is_safe_without_n8n_config():
    if server.N8N_ALLOWED_WORKFLOWS:
        return
    result = asyncio.run(server.n8n_list_allowed_workflows())
    assert result["workflows"] == []
    assert "Nenhum workflow" in result["message"]


def test_empty_execution_list_is_safe_without_n8n_config():
    if server.N8N_ALLOWED_WORKFLOWS:
        return
    result = asyncio.run(server.n8n_recent_executions())
    assert result["executions"] == []
