"""Register the Cloud Run MCP Server and its tools into Google Cloud Agent Registry.

Extracts tool specifications dynamically from the FastMCP server instance and registers
them with the Agent Registry API (agentregistry.googleapis.com), exposing the MCP server
and tools in the Gemini Enterprise Agent Platform catalog.
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

import os

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import google.auth
from google.auth.transport.requests import Request

# Import the local FastMCP server instance
try:
    from mcp_server.server import mcp
except ImportError:
    from server import mcp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp_server.register")

API_BASE = "https://agentregistry.googleapis.com/v1"


def get_access_token() -> str:
    """Retrieve a fresh Google OAuth2 access token via Application Default Credentials."""
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(Request())
    return creds.token


def get_cloud_run_url(service_name: str, project_id: str, location: str, fallback_on_error: bool = False) -> str:
    """Query the Cloud Run service URL using gcloud."""
    logger.info(f"Resolving Cloud Run endpoint for service '{service_name}'...")
    cmd = [
        "gcloud",
        "run",
        "services",
        "describe",
        service_name,
        f"--project={project_id}",
        f"--region={location}",
        "--format=value(status.url)",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        url = proc.stdout.strip()
        if url:
            return url
    except Exception as e:
        logger.debug(f"Cloud Run URL resolution failed: {e}")

    if fallback_on_error:
        placeholder = f"https://{service_name}-placeholder.{location}.run.app"
        logger.info(f"Using fallback Cloud Run URL for '{service_name}': {placeholder}")
        return placeholder

    raise ValueError(f"Could not determine URL for Cloud Run service '{service_name}'.")


async def extract_tool_specs() -> List[Dict[str, Any]]:
    """Extract tool schemas directly from the FastMCP server instance."""
    tools = await mcp.list_tools()
    tool_specs: List[Dict[str, Any]] = []

    for t in tools:
        spec: Dict[str, Any] = {
            "name": t.name,
            "description": t.description or "",
        }
        # Extract input schema
        if hasattr(t, "inputSchema") and t.inputSchema:
            spec["inputSchema"] = t.inputSchema
        elif hasattr(t, "parameters") and t.parameters:
            spec["inputSchema"] = t.parameters
        else:
            spec["inputSchema"] = {"type": "object"}

        tool_specs.append(spec)

    logger.info(f"Extracted {len(tool_specs)} tools from FastMCP server: {[t['name'] for t in tool_specs]}")
    return tool_specs


def wait_for_operation(operation_name: str, token: str, timeout_seconds: int = 60) -> Dict[str, Any]:
    """Poll a Long Running Operation until completion."""
    url = f"https://agentregistry.googleapis.com/v1/{operation_name}"
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("done"):
            if "error" in data:
                raise RuntimeError(f"Operation failed: {json.dumps(data['error'])}")
            logger.info("Operation completed successfully.")
            return data.get("response", {})

        time.sleep(1.0)

    raise TimeoutError(f"Operation {operation_name} timed out after {timeout_seconds} seconds.")


def service_exists(project_id: str, location: str, service_id: str, token: str) -> bool:
    """Check if a service already exists in Agent Registry."""
    url = f"{API_BASE}/projects/{project_id}/locations/{location}/services/{service_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def delete_service(project_id: str, location: str, service_id: str, token: str) -> None:
    """Delete an existing service in Agent Registry."""
    url = f"{API_BASE}/projects/{project_id}/locations/{location}/services/{service_id}"
    logger.info(f"Deleting existing service '{service_id}' to update catalog...")
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        op = json.loads(resp.read().decode("utf-8"))

    if not op.get("done") and "name" in op:
        wait_for_operation(op["name"], token)


def register_mcp_server(
    project_id: str,
    location: str,
    service_id: str,
    display_name: str,
    description: str,
    mcp_endpoint_url: str,
    tool_specs: List[Dict[str, Any]],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Register or recreate the MCP server service in Google Cloud Agent Registry."""
    payload = {
        "displayName": display_name,
        "description": description,
        "interfaces": [
            {
                "protocolBinding": "JSONRPC",
                "url": mcp_endpoint_url,
            }
        ],
        "mcpServerSpec": {
            "type": "TOOL_SPEC",
            "content": {
                "tools": tool_specs,
            },
        },
    }

    if dry_run:
        logger.info("[DRY RUN] Would register Service payload:")
        print(json.dumps(payload, indent=2))
        return {"dry_run": True, "payload": payload}

    token = get_access_token()

    # Recreate service if it exists to ensure clean schema update
    if service_exists(project_id, location, service_id, token):
        delete_service(project_id, location, service_id, token)

    parent = f"projects/{project_id}/locations/{location}"
    create_url = f"{API_BASE}/{parent}/services?serviceId={service_id}"

    logger.info(f"Registering MCP Service '{service_id}' at {mcp_endpoint_url}...")
    req = urllib.request.Request(
        create_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            op = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        logger.error(f"HTTP {e.code} Error registering service: {err_msg}")
        raise

    if not op.get("done") and "name" in op:
        logger.info(f"Waiting for LRO {op['name']}...")
        result = wait_for_operation(op["name"], token)
    else:
        result = op.get("response", op)

    registry_resource = result.get("registryResource")
    logger.info(f"Service successfully registered!")
    logger.info(f"Agent Registry Resource: {registry_resource}")
    return result


async def main_async():
    parser = argparse.ArgumentParser(
        description="Register Cloud Run MCP Server with Google Cloud Agent Registry."
    )
    parser.add_argument("--project", default=None, help="Google Cloud Project ID")
    parser.add_argument("--location", default="us-central1", help="Google Cloud Region")
    parser.add_argument("--service-id", default="customer-banking-mcp", help="Service ID in Agent Registry")
    parser.add_argument("--cloud-run-service", default="customer-policy-mcp-service", help="Cloud Run service name")
    parser.add_argument("--mcp-url", default=None, help="Direct URL to /mcp endpoint (overrides Cloud Run query)")
    parser.add_argument("--display-name", default="Customer Banking MCP Server", help="Display name in catalog")
    parser.add_argument(
        "--description",
        default="Enterprise banking MCP server governing wire transfers and customer account operations.",
        help="Service description",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payload without executing API call")

    args = parser.parse_args()

    # Determine project ID
    project = args.project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        try:
            _, project = google.auth.default()
        except Exception:
            pass
    if not project:
        parser.error("--project or GOOGLE_CLOUD_PROJECT environment variable is required.")

    # Determine endpoint URL
    if args.mcp_url:
        endpoint = args.mcp_url
    else:
        base_url = get_cloud_run_url(
            args.cloud_run_service, project, args.location, fallback_on_error=args.dry_run
        )
        endpoint = f"{base_url.rstrip('/')}/mcp"

    tool_specs = await extract_tool_specs()

    result = register_mcp_server(
        project_id=project,
        location=args.location,
        service_id=args.service_id,
        display_name=args.display_name,
        description=args.description,
        mcp_endpoint_url=endpoint,
        tool_specs=tool_specs,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 60)
    print("Agent Registry MCP Server Registration Summary:")
    print(f"Service ID:       {args.service_id}")
    print(f"Endpoint URL:     {endpoint}")
    print(f"Tools Registered: {len(tool_specs)} ({', '.join(t['name'] for t in tool_specs)})")
    if result.get("registryResource"):
        print(f"Registry Resource: {result.get('registryResource')}")
    print("=" * 60)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
