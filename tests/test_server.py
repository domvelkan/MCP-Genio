import asyncio
import os

os.environ.setdefault("GENIO_MCP_TOKEN", "test-token-" + "x" * 40)
os.environ.setdefault("TELEGRAM_ALLOWED_CHAT_IDS", "12345")
import server


def test_service_name():
    assert server.APP_NAME == "MCP-Genio"


def test_unknown_workflow_not_allowed():
    assert "workflow-not-approved" not in server.N8N_ALLOWED_WORKFLOWS


def test_cockpit_rejects_unapproved_chat():
    try:
        asyncio.run(server.process_cockpit_command("99999", "/cockpit status"))
    except PermissionError:
        pass
    else:
        raise AssertionError("unapproved chat should be rejected")


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
