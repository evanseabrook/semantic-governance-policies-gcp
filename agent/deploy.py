"""Deployment script to package and deploy the ADK Agent to Vertex AI Agent Engine.

Configures the agent with AGENT_IDENTITY and connects it to the Agent Gateway
governing tool invocations to the Cloud Run MCP server.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Ensure project root is prioritized in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
agent_dir = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] == agent_dir:
    sys.path.pop(0)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import vertexai
from vertexai import agent_engines
from vertexai.agent_engines import AdkApp

try:
    from agent.agent import create_agent
except (ImportError, ModuleNotFoundError):
    from agent import create_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent.deploy")

REQUIREMENTS = [
    "google-adk>=2.12.0",
    "mcp>=1.3.0,<2.0.0",
    "google-cloud-aiplatform>=2.6.0",
    "pydantic>=2.0.0",
    "google-auth>=2.30.0",
    "httpx>=0.27.0",
    "cloudpickle>=3.0.0",
    "a2a-sdk>=1.3.0",
    "google-cloud-agentidentitycredentials>=0.1.2",
    "google-cloud-iamconnectorcredentials>=0.1.2",
    "opentelemetry-instrumentation-google-genai>=0.7b1",
    "opentelemetry-instrumentation-sqlite3>=0.63b1",
    "opentelemetry-exporter-otlp-proto-grpc>=1.42.1",
    "opentelemetry-exporter-otlp-proto-http>=1.42.1",
    "opentelemetry-instrumentation-vertexai>=2.0b0",
]



def get_agent_identity_principal(
    resource_name: str,
    project_id: str,
    location: str,
) -> str:
    """Derive the SPIFFE principal URI for a Vertex AI Agent Engine instance.

    Format:
    - Organization-based project:
      principal://agents.global.org-<ORG_ID>.system.id.goog/resources/aiplatform/projects/<PROJECT_NUMBER>/locations/<LOCATION>/reasoningEngines/<ENGINE_ID>
    - Standalone project:
      principal://agents.global.proj-<PROJECT_NUMBER>.system.id.goog/resources/aiplatform/projects/<PROJECT_NUMBER>/locations/<LOCATION>/reasoningEngines/<ENGINE_ID>
    """
    engine_id = resource_name.split("/")[-1]
    cmd = ["gcloud", "projects", "describe", project_id, "--format=json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    project_info = json.loads(proc.stdout)
    project_number = project_info.get("projectNumber", "")
    parent = project_info.get("parent", {})

    if parent.get("type") == "organization" and parent.get("id"):
        trust_domain = f"org-{parent['id']}"
    else:
        trust_domain = f"proj-{project_number}"

    return (
        f"principal://agents.global.{trust_domain}.system.id.goog/"
        f"resources/aiplatform/projects/{project_number}/locations/{location}/reasoningEngines/{engine_id}"
    )


def grant_agent_invoker_permission(
    resource_name: str,
    project_id: str,
    location: str,
    service_name: str = "customer-policy-mcp-service",
    identity_type: str = "AGENT_IDENTITY",
    service_account: Optional[str] = None,
) -> Optional[str]:
    """Grant Cloud Run Invoker (roles/run.invoker) to the deployed agent's identity."""
    try:
        if identity_type == "AGENT_IDENTITY":
            member = get_agent_identity_principal(
                resource_name=resource_name,
                project_id=project_id,
                location=location,
            )
        elif service_account:
            member = f"serviceAccount:{service_account}"
        else:
            logger.warning("No Agent Identity or Service Account available to grant permissions.")
            return None

        logger.info(
            f"Granting roles/run.invoker on Cloud Run service '{service_name}' "
            f"to member '{member}'..."
        )
        cmd = [
            "gcloud",
            "run",
            "services",
            "add-iam-policy-binding",
            service_name,
            f"--region={location}",
            f"--project={project_id}",
            f"--member={member}",
            "--role=roles/run.invoker",
            "--quiet",
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Successfully granted roles/run.invoker to {member} on {service_name}.")
        return member
    except Exception as e:
        logger.error(f"Failed to automatically grant Cloud Run invoker permissions: {e}")
        return None


def deploy_to_agent_engine(
    project_id: str,
    location: str,
    staging_bucket: str,
    gateway_url: Optional[str] = None,
    mcp_server_name: Optional[str] = "customer-banking-mcp",
    service_account: Optional[str] = None,
    display_name: str = "customer-policy-agent",
    model_name: str = "gemini-3.8-flash",
    identity_type: str = "AGENT_IDENTITY",
    cloud_run_service: str = "customer-policy-mcp-service",
    skip_iam: bool = False,
    dry_run: bool = False,
) -> str:
    """Deploy or update the ADK agent on Vertex AI Agent Engine.

    If an agent with `display_name` is already deployed, it updates the existing
    resource in-place to avoid deploying duplicate sibling agents. Upon successful
    deployment, it automatically grants the Agent Identity `roles/run.invoker`
    on the target Cloud Run MCP server.

    Args:
        project_id: GCP project ID (e.g. 'my-project-id')
        location: GCP region (e.g. 'us-central1')
        staging_bucket: GCS bucket for staging artifacts (e.g. 'gs://your-staging-bucket')
        gateway_url: Optional fallback URL for Agent Gateway or Cloud Run MCP service
        mcp_server_name: Google Cloud Agent Registry MCP Server name or service ID
        service_account: Optional IAM Service Account (mutually exclusive with AGENT_IDENTITY)
        display_name: Human-readable display name for the Reasoning Engine resource
        model_name: The Gemini model version (default: 'gemini-3.8-flash')
        identity_type: Workload identity type ('AGENT_IDENTITY' or 'DEFAULT')
        cloud_run_service: Target Cloud Run MCP service name (default: 'customer-policy-mcp-service')
        skip_iam: If True, skip post-deployment run.invoker IAM binding
        dry_run: If True, validate local agent creation and packaging without remote deploy

    Returns:
        Resource name of the deployed or updated Agent Engine.
    """
    logger.info(f"Initializing Vertex AI for project '{project_id}' in '{location}'...")
    if not dry_run:
        vertexai.init(
            project=project_id,
            location=location,
            staging_bucket=staging_bucket,
        )

    target_desc = f"Agent Registry MCP server '{mcp_server_name}'" if mcp_server_name else f"Gateway at '{gateway_url}'"
    logger.info(f"Instantiating ADK Agent targeting {target_desc} with model '{model_name}'...")
    agent = create_agent(
        gateway_url=gateway_url,
        mcp_server_name=mcp_server_name,
        model_name=model_name,
    )

    # Wrap the ADK Agent in AdkApp for Vertex AI Agent Engine execution
    app = AdkApp(agent=agent)

    # Load opentelemetry.env if present
    env_file_path = os.path.join(os.getcwd(), "opentelemetry.env")
    if os.path.exists(env_file_path):
        with open(env_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k not in os.environ:
                    os.environ[k] = v

    env_vars = {
        "GCP_PROJECT": project_id,
        "GCP_LOCATION": location,
        "USE_AGENT_REGISTRY": "true" if mcp_server_name else "false",
        "MCP_SERVER_NAME": mcp_server_name or "",
        "GATEWAY_URL": gateway_url or "",
        "GEMINI_LOCATION": "global",
        "OTEL_SERVICE_NAME": os.environ.get("OTEL_SERVICE_NAME", display_name),
        "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED": os.environ.get(
            "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED", "true"
        ),
        "OTEL_SEMCONV_STABILITY_OPT_IN": os.environ.get(
            "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
        ),
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": os.environ.get(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "EVENT_ONLY"
        ),
        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": os.environ.get(
            "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false"
        ),
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": os.environ.get(
            "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", "true"
        ),
        "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
    }
    env_vars = {k: v for k, v in env_vars.items() if v}

    if dry_run:
        logger.info("[DRY-RUN] Validation successful! AdkApp instantiated cleanly.")
        logger.info(f"[DRY-RUN] Project: {project_id} | Location: {location}")
        logger.info(f"[DRY-RUN] Staging Bucket: {staging_bucket}")
        logger.info(f"[DRY-RUN] MCP Server Name: {mcp_server_name}")
        logger.info(f"[DRY-RUN] Gateway URL: {gateway_url}")
        logger.info(f"[DRY-RUN] Identity Type: {identity_type}")
        logger.info(f"[DRY-RUN] Agent Framework: {getattr(app, 'agent_framework', 'google-adk')}")
        if not skip_iam:
            logger.info(
                f"[DRY-RUN] Post-deployment IAM step: Would grant 'roles/run.invoker' "
                f"on Cloud Run service '{cloud_run_service}' to Agent Identity."
            )
        try:
            vertexai.init(project=project_id, location=location)
            matched = [
                eng for eng in agent_engines.list()
                if eng.display_name == display_name
            ]
            if matched:
                logger.info(f"[DRY-RUN] Found existing Agent Engine: {matched[0].resource_name}. Plan: UPDATE in-place.")
                return matched[0].resource_name
            else:
                logger.info(f"[DRY-RUN] No existing Agent Engine with display_name='{display_name}'. Plan: CREATE new agent.")
                return f"projects/{project_id}/locations/{location}/reasoningEngines/dry-run-preview"
        except Exception as e:
            logger.info(f"[DRY-RUN] Remote lookup skipped or failed ({e}). Returning preview ID.")
            return f"projects/{project_id}/locations/{location}/reasoningEngines/dry-run-preview"

    # In Vertex AI Agent Engine, service_account must NOT be specified when identity_type is AGENT_IDENTITY
    effective_sa = None if identity_type == "AGENT_IDENTITY" else service_account
    if identity_type == "AGENT_IDENTITY" and service_account:
        logger.info("identity_type is AGENT_IDENTITY: omitting service_account to use resource-scoped Agent Identity.")

    description = (
        "Policy-governed ADK Customer Support Agent connected via Agent Gateway "
        "to Cloud Run MCP with Semantic Governance natural language constraints."
    )

    logger.info(f"Querying existing Agent Engines for display_name='{display_name}'...")
    existing_engines = [
        eng for eng in agent_engines.list()
        if eng.display_name == display_name
    ]

    if existing_engines:
        existing_engine = sorted(
            existing_engines,
            key=lambda e: (
                getattr(e.gca_resource, "update_time", None)
                or getattr(e.gca_resource, "create_time", None)
            ),
            reverse=True,
        )[0]
        resource_name = existing_engine.resource_name
        logger.info(
            f"Found existing Agent Engine '{resource_name}' with display_name='{display_name}'. "
            f"Updating agent in-place to avoid duplicate sibling deployments..."
        )
        remote_engine = agent_engines.update(
            resource_name=resource_name,
            agent_engine=app,
            requirements=REQUIREMENTS,
            extra_packages=["agent"],
            display_name=display_name,
            description=description,
            env_vars=env_vars,
            service_account=effective_sa,
            identity_type=identity_type,
        )
        logger.info(f"Successfully updated Agent Engine in-place: {remote_engine.resource_name}")
    else:
        logger.info(
            f"No existing Agent Engine found with display_name='{display_name}'. "
            "Deploying net new Agent Engine..."
        )
        remote_engine = agent_engines.create(
            agent_engine=app,
            requirements=REQUIREMENTS,
            extra_packages=["agent"],
            display_name=display_name,
            description=description,
            env_vars=env_vars,
            service_account=effective_sa,
            identity_type=identity_type,
        )
        logger.info(f"Successfully deployed Agent Engine: {remote_engine.resource_name}")

    deployed_resource = remote_engine.resource_name

    # Post-deployment: automatically grant run.invoker permission on the target Cloud Run service
    if not skip_iam:
        logger.info("Executing post-deployment IAM binding to grant run.invoker on Cloud Run...")
        grant_agent_invoker_permission(
            resource_name=deployed_resource,
            project_id=project_id,
            location=location,
            service_name=cloud_run_service,
            identity_type=identity_type,
            service_account=effective_sa,
        )

    return deployed_resource


def main():
    parser = argparse.ArgumentParser(description="Deploy ADK Agent to Vertex AI Agent Engine")
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        help="Google Cloud Project ID",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GOOGLE_CLOUD_REGION", "us-central1"),
        help="Google Cloud Region",
    )
    parser.add_argument(
        "--staging-bucket",
        default=os.environ.get("STAGING_BUCKET"),
        help="GCS staging bucket (defaults to gs://{project}-agent-engine-staging)",
    )
    parser.add_argument(
        "--mcp-server-name",
        default=os.environ.get("MCP_SERVER_NAME", "customer-banking-mcp"),
        help="Agent Registry MCP Server resource name or service ID (default: 'customer-banking-mcp')",
    )
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("GATEWAY_URL"),
        required=False,
        help="Optional fallback URL for direct MCP connection (e.g. http://localhost:8080/mcp)",
    )
    parser.add_argument(
        "--service-account",
        default=os.environ.get("AGENT_ENGINE_SA"),
        help="Agent Engine Service Account email (omitted when identity-type is AGENT_IDENTITY)",
    )
    parser.add_argument(
        "--identity-type",
        default="AGENT_IDENTITY",
        choices=["AGENT_IDENTITY", "DEFAULT"],
        help="Identity type for runtime execution (default: 'AGENT_IDENTITY')",
    )
    parser.add_argument(
        "--display-name",
        default="customer-policy-agent",
        help="Display name for the deployed agent resource",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        help="Gemini model version (default: 'gemini-3.8-flash')",
    )
    parser.add_argument(
        "--cloud-run-service",
        default=os.environ.get("CLOUD_RUN_SERVICE", "customer-policy-mcp-service"),
        help="Target Cloud Run service name for MCP tool server",
    )
    parser.add_argument(
        "--skip-iam",
        action="store_true",
        help="Skip post-deployment IAM binding of run.invoker to the Agent Identity",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate agent packaging and configuration locally without submitting remote deploy",
    )

    args = parser.parse_args()

    if not args.project:
        parser.error("--project or GOOGLE_CLOUD_PROJECT environment variable is required.")

    staging_bucket = args.staging_bucket or f"gs://{args.project}-agent-engine-staging"

    resource_name = deploy_to_agent_engine(
        project_id=args.project,
        location=args.location,
        staging_bucket=staging_bucket,
        gateway_url=args.gateway_url,
        mcp_server_name=args.mcp_server_name,
        service_account=args.service_account,
        display_name=args.display_name,
        model_name=args.model,
        identity_type=args.identity_type,
        cloud_run_service=args.cloud_run_service,
        skip_iam=args.skip_iam,
        dry_run=args.dry_run,
    )
    print(f"\nDeployment Completed!\nAgent Resource Name: {resource_name}")


if __name__ == "__main__":
    main()
