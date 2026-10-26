import os

os.environ.setdefault('GENIO_MCP_TOKEN', 'test-token-' + 'x' * 40)
import server


def test_service_name():
    assert server.APP_NAME == 'MCP-Genio'


def test_unknown_workflow_not_allowed():
    assert 'workflow-not-approved' not in server.N8N_ALLOWED_WORKFLOWS
