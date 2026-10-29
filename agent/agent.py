"""Policy-Aware ADK Agent for Vertex AI Agent Engine.

Operates with Gemini 3.8 Flash and interacts with Cloud Run MCP tools
routed through Agent Gateway under Semantic Governance policies.
"""

import logging
import os
from typing import Any, Dict, Optional, Union

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

try:
    from agent.auth import DynamicAuthHeaders, get_gateway_auth_headers
except (ImportError, ModuleNotFoundError):
    from auth import DynamicAuthHeaders, get_gateway_auth_headers

logger = logging.getLogger("agent")



class GlobalGemini(Gemini):
    """ADK Gemini model integration routed to the global location endpoint.

    On Gemini Enterprise Agent Platform, Gemini 3.x models (such as gemini-3.8-flash)
    are hosted on the global endpoint (`locations/global`), rather than regional
    endpoints like `us-central1`.
    """

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.model == other
        if isinstance(other, Gemini):
            return self.model == other.model
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.model)


def _make_header_provider(url: str):
    def provider(readonly_context: Optional[Any] = None) -> Dict[str, str]:
        return get_gateway_auth_headers(url)
    return provider




SYSTEM_INSTRUCTION = """You are an enterprise Customer Financial & Operations Agent.

You assist customers with looking up their account details, checking recent transaction histories, and initiating wire transfers using your available banking tools.

Tools:
- `get_customer_overview`: Retrieve customer tier, status, balance, and account details.
- `list_customer_transactions`: Retrieve recent settled or pending transaction records.
- `initiate_wire_transfer`: Execute an outbound wire transfer from customer funds as requested by the customer.

Instructions:
1. When a customer requests an account overview or transaction history, invoke the corresponding lookup tool.
2. When a customer asks to initiate or send a wire transfer, invoke `initiate_wire_transfer` with the provided parameters.
3. If a tool invocation is denied or returns an error, communicate the message clearly to the customer without retrying the failed call.
4. Always rely exclusively on verified tool results. Never hallucinate balances, transaction IDs, or transfer confirmations.
"""



def _resolve_agent_registry_mcp_server(
    registry: Any, query: Optional[str] = None
) -> Optional[str]:
    """Resolve the MCP Server resource name from Agent Registry."""
    if query and query.startswith("projects/"):
        return query
    try:
        data = registry._make_request("mcpServers")
        servers = data.get("mcpServers", [])
        for s in servers:
            name = s.get("name", "")
            disp = s.get("displayName", "")
            mid = s.get("mcpServerId", "")
            if query and (query in name or query in disp or query in mid):
                return name
            if not query and ("customer-banking-mcp" in mid or "Customer Banking" in disp):
                return name
        if servers and not query:
            return servers[0].get("name")
    except Exception as e:
        logger.debug(f"Agent Registry MCP server lookup: {e}")
    return None


def create_agent(
    gateway_url: Optional[str] = None,
    mcp_server_name: Optional[str] = None,
    model_name: Optional[Union[str, Gemini]] = None,
) -> LlmAgent:
    """Build and configure the policy-aware ADK Agent.

    Args:
        gateway_url: Optional direct Gateway or MCP URL (fallback for local dev/testing).
        mcp_server_name: Agent Registry MCP Server resource name or service ID.
        model_name: The Gemini model version (default: 'gemini-3.8-flash' or GEMINI_MODEL env var).

    Returns:
        Configured LlmAgent instance.
    """
    selected_model_name = (
        model_name if isinstance(model_name, str)
        else (model_name.model if isinstance(model_name, Gemini) else None)
    ) or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_LOCATION", os.environ.get("LOCATION", "us-central1"))
    gemini_location = os.environ.get("GEMINI_LOCATION", "global")
    server_resource = mcp_server_name or os.environ.get("MCP_SERVER_NAME")
    use_agent_registry = os.environ.get("USE_AGENT_REGISTRY", "true").lower() in ("true", "1", "yes")

    logger.info(
        f"Configuring ADK Agent with model '{selected_model_name}' (location: {gemini_location}, project: {project})"
    )

    if isinstance(model_name, Gemini):
        model_instance = model_name
    else:
        model_instance = GlobalGemini(
            model=selected_model_name,
            client_kwargs={
                "vertexai": True,
                "project": project,
                "location": gemini_location,
            },
        )

    mcp_toolset = None

    # Priority 1: Use Google Cloud Agent Registry when running in cloud or not explicitly targeting localhost
    if use_agent_registry and not (gateway_url and "localhost" in gateway_url):
        try:
            from google.adk.integrations.agent_registry.agent_registry import AgentRegistry

            target_audience = (
                gateway_url
                or os.environ.get("GATEWAY_URL")
                or os.environ.get("MCP_SERVER_URL", "")
            )
            registry = AgentRegistry(
                project_id=project,
                location=location,
                header_provider=_make_header_provider(target_audience),
            )
            resolved_server = _resolve_agent_registry_mcp_server(registry, server_resource)
            if resolved_server:
                logger.info(f"Loading tools from Google Cloud Agent Registry: {resolved_server}")
                mcp_toolset = registry.get_mcp_toolset(resolved_server)
                mcp_toolset._connection_params.headers = DynamicAuthHeaders(target_audience)
                mcp_toolset._connection_params.timeout = 30.0
        except Exception as e:
            logger.warning(f"Could not load tools from Agent Registry, falling back to direct URL: {e}")

    # Priority 2: Fallback to direct Streamable HTTP MCP (local dev, mock servers, offline tests)
    if mcp_toolset is None:
        target_url = (
            gateway_url
            or os.environ.get("GATEWAY_URL")
            or os.environ.get("MCP_SERVER_URL", "http://localhost:8080/mcp")
        )
        logger.info(f"Connecting to MCP via Streamable HTTP URL: {target_url}")
        connection_params = StreamableHTTPConnectionParams(
            url=target_url,
            headers=DynamicAuthHeaders(target_url),
            timeout=30.0,
        )
        mcp_toolset = McpToolset(
            connection_params=connection_params,
            header_provider=_make_header_provider(target_url),
        )

    agent = LlmAgent(
        name="customer_governed_agent",
        description="Policy-governed customer support and account operations agent.",
        model=model_instance,
        instruction=SYSTEM_INSTRUCTION,
        tools=[mcp_toolset],
    )

    return agent


if __name__ == "__main__":
    agent = create_agent()
    print(f"Agent successfully initialized: {agent.name} (model={agent.model})")

