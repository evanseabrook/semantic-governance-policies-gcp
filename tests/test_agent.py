"""Unit tests for the policy-aware ADK Agent."""

from agent.agent import create_agent
from agent.auth import get_gateway_auth_headers, get_oidc_token


def test_auth_headers_generation():
    headers = get_gateway_auth_headers("http://localhost:8080/mcp")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["X-Agent-Identity"] == "adk-customer-support-agent"


def test_agent_initialization():
    agent = create_agent(
        gateway_url="http://localhost:8080/mcp",
        model_name="gemini-3.8-flash",
    )
    assert agent.name == "customer_governed_agent"
    assert agent.model == "gemini-3.8-flash"
    assert len(agent.tools) == 1
    assert "banking" in agent.instruction.lower()
    assert "initiate_wire_transfer" in agent.instruction


def test_agent_default_model():
    agent = create_agent(gateway_url="http://localhost:8080/mcp")
    assert agent.model == "gemini-3.8-flash"


def test_adk_app_framework_spec():
    from vertexai.agent_engines import AdkApp
    agent = create_agent(gateway_url="http://localhost:8080/mcp")
    app = AdkApp(agent=agent)
    assert getattr(app, "agent_framework", None) == "google-adk"


def test_deploy_dry_run():
    from agent.deploy import deploy_to_agent_engine
    resource_name = deploy_to_agent_engine(
        project_id="test-project",
        location="us-central1",
        staging_bucket="gs://test-project-agent-engine-staging",
        gateway_url="http://localhost:8080/mcp",
        dry_run=True,
    )
    assert "reasoningEngines" in resource_name


def test_deploy_dry_run_with_agent_registry():
    from agent.deploy import deploy_to_agent_engine
    resource_name = deploy_to_agent_engine(
        project_id="test-project",
        location="us-central1",
        staging_bucket="gs://test-project-agent-engine-staging",
        mcp_server_name="customer-banking-mcp",
        dry_run=True,
    )
    assert "reasoningEngines" in resource_name


def test_deploy_updates_existing_agent(monkeypatch):
    from unittest.mock import MagicMock
    import vertexai
    from vertexai import agent_engines
    import agent.deploy as deploy_mod
    from agent.deploy import deploy_to_agent_engine

    mock_engine = MagicMock()
    mock_engine.display_name = "customer-policy-agent"
    mock_engine.resource_name = "projects/123/locations/us-central1/reasoningEngines/456"
    mock_engine.gca_resource.update_time = "2026-10-22T20:00:00Z"
    mock_engine.gca_resource.create_time = "2026-10-22T19:00:00Z"

    mock_updated_engine = MagicMock()
    mock_updated_engine.resource_name = "projects/123/locations/us-central1/reasoningEngines/456"

    mock_list = MagicMock(return_value=[mock_engine])
    mock_update = MagicMock(return_value=mock_updated_engine)
    mock_create = MagicMock()
    mock_grant_iam = MagicMock()

    monkeypatch.setattr(vertexai, "init", MagicMock())
    monkeypatch.setattr(agent_engines, "list", mock_list)
    monkeypatch.setattr(agent_engines, "update", mock_update)
    monkeypatch.setattr(agent_engines, "create", mock_create)
    monkeypatch.setattr(deploy_mod, "grant_agent_invoker_permission", mock_grant_iam)

    result = deploy_to_agent_engine(
        project_id="test-proj",
        location="us-central1",
        staging_bucket="gs://test-bucket",
        gateway_url="http://test-gw/mcp",
        mcp_server_name="customer-banking-mcp",
        dry_run=False,
    )

    assert result == "projects/123/locations/us-central1/reasoningEngines/456"
    assert mock_update.call_count == 1
    assert mock_create.call_count == 0
    assert mock_grant_iam.call_count == 1
    mock_grant_iam.assert_called_with(
        resource_name="projects/123/locations/us-central1/reasoningEngines/456",
        project_id="test-proj",
        location="us-central1",
        service_name="customer-policy-mcp-service",
        identity_type="AGENT_IDENTITY",
        service_account=None,
    )

    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["resource_name"] == "projects/123/locations/us-central1/reasoningEngines/456"
    assert call_kwargs["display_name"] == "customer-policy-agent"
    assert call_kwargs["env_vars"]["USE_AGENT_REGISTRY"] == "true"
    assert call_kwargs["env_vars"]["MCP_SERVER_NAME"] == "customer-banking-mcp"
    assert call_kwargs["env_vars"]["GATEWAY_URL"] == "http://test-gw/mcp"
    assert call_kwargs["identity_type"] == "AGENT_IDENTITY"
    assert call_kwargs["service_account"] is None


def test_deploy_creates_new_agent_when_none_exists(monkeypatch):
    from unittest.mock import MagicMock
    import vertexai
    from vertexai import agent_engines
    import agent.deploy as deploy_mod
    from agent.deploy import deploy_to_agent_engine

    mock_new_engine = MagicMock()
    mock_new_engine.resource_name = "projects/123/locations/us-central1/reasoningEngines/789"

    mock_list = MagicMock(return_value=[])
    mock_update = MagicMock()
    mock_create = MagicMock(return_value=mock_new_engine)
    mock_grant_iam = MagicMock()

    monkeypatch.setattr(vertexai, "init", MagicMock())
    monkeypatch.setattr(agent_engines, "list", mock_list)
    monkeypatch.setattr(agent_engines, "update", mock_update)
    monkeypatch.setattr(agent_engines, "create", mock_create)
    monkeypatch.setattr(deploy_mod, "grant_agent_invoker_permission", mock_grant_iam)

    result = deploy_to_agent_engine(
        project_id="test-proj",
        location="us-central1",
        staging_bucket="gs://test-bucket",
        gateway_url="http://test-gw/mcp",
        dry_run=False,
    )

    assert result == "projects/123/locations/us-central1/reasoningEngines/789"
    assert mock_create.call_count == 1
    assert mock_update.call_count == 0
    assert mock_grant_iam.call_count == 1

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["display_name"] == "customer-policy-agent"
    assert call_kwargs["env_vars"]["GATEWAY_URL"] == "http://test-gw/mcp"
    assert call_kwargs["identity_type"] == "AGENT_IDENTITY"


def test_get_agent_identity_principal(monkeypatch):
    import subprocess
    import json
    from unittest.mock import MagicMock
    from agent.deploy import get_agent_identity_principal

    mock_proc = MagicMock()
    mock_proc.stdout = json.dumps({
        "projectNumber": "1234567890",
        "parent": {"id": "999888777", "type": "organization"}
    })
    monkeypatch.setattr(subprocess, "run", MagicMock(return_value=mock_proc))

    principal = get_agent_identity_principal(
        resource_name="projects/1234567890/locations/us-central1/reasoningEngines/my-agent-123",
        project_id="my-project",
        location="us-central1",
    )
    expected = (
        "principal://agents.global.org-999888777.system.id.goog/"
        "resources/aiplatform/projects/1234567890/locations/us-central1/reasoningEngines/my-agent-123"
    )
    assert principal == expected

