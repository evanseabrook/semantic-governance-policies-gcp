"""Deployment script for Semantic Governance Policies on Gemini Enterprise Agent Platform.

Validates declarative Semantic Governance Policy YAML files and registers them with
the Vertex AI / Agent Platform Semantic Governance Policy API.
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("policies.deploy")


def validate_policy_schema(policy_data: Dict[str, Any], file_path: Path) -> None:
    """Validate that the policy YAML conforms to Google Cloud's Semantic Governance Policy schema."""
    if not isinstance(policy_data, dict):
        raise ValueError(f"{file_path.name}: Root of policy YAML must be a mapping/dictionary.")

    policy_id = policy_data.get("id")
    if not policy_id or not isinstance(policy_id, str):
        raise ValueError(f"{file_path.name}: Missing or invalid 'id' field.")

    if not re.match(r"^[a-z0-9-]+$", policy_id):
        raise ValueError(
            f"{file_path.name}: Policy ID '{policy_id}' must contain only lowercase letters, numbers, and hyphens."
        )

    constraint = policy_data.get("naturalLanguageConstraint")
    if not constraint or not isinstance(constraint, str) or not constraint.strip():
        raise ValueError(f"{file_path.name}: Missing or empty 'naturalLanguageConstraint'.")

    if len(constraint) > 5000:
        raise ValueError(f"{file_path.name}: 'naturalLanguageConstraint' exceeds 5,000 character limit.")

    agent = policy_data.get("agent")
    if agent and (not isinstance(agent, str) or not agent.startswith("projects/")):
        raise ValueError(f"{file_path.name}: 'agent' must be a fully-qualified resource URI (projects/.../agents/...).")

    customization = policy_data.get("agentResponseCustomization")
    if customization:
        if not isinstance(customization, dict):
            raise ValueError(f"{file_path.name}: 'agentResponseCustomization' must be a dictionary.")
        denial = customization.get("denialMessage")
        if denial and len(denial) > 1000:
            raise ValueError(f"{file_path.name}: 'denialMessage' exceeds 1,000 character limit.")


def load_policy(file_path: Path) -> Dict[str, Any]:
    """Load and validate a single policy YAML file."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    validate_policy_schema(data, file_path)
    return data


def load_all_policies(policy_dir: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    """Scan directory and load all valid Semantic Governance Policy YAML files."""
    if not policy_dir.is_dir():
        raise FileNotFoundError(f"Policy directory does not exist: {policy_dir}")

    policy_files = sorted(
        [p for p in policy_dir.iterdir() if p.suffix in (".yaml", ".yml") and not p.name.startswith(".")]
    )

    policies = []
    for p in policy_files:
        try:
            data = load_policy(p)
            policies.append((p, data))
        except Exception as e:
            logger.error(f"Error loading {p.name}: {e}")
            raise

    return policies


def resolve_agent_registry_id(project_id: str, location: str, token: str) -> Optional[str]:
    """Query Agent Registry to auto-discover registered agent or mcpServer resource ID."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=10.0) as client:
            url = f"https://agentregistry.googleapis.com/v1/projects/{project_id}/locations/{location}/agents"
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                agents = data.get("agents", [])
                if agents:
                    return agents[0]["name"].split("/")[-1]
            mcp_url = f"https://agentregistry.googleapis.com/v1/projects/{project_id}/locations/{location}/mcpServers"
            mcp_resp = client.get(mcp_url, headers=headers)
            if mcp_resp.status_code == 200:
                mcp_data = mcp_resp.json()
                servers = mcp_data.get("mcpServers", [])
                if servers:
                    return servers[0]["name"].split("/")[-1]
    except Exception as e:
        logger.debug(f"Agent Registry auto-discovery skipped: {e}")
    return None


def build_api_payload(
    policy_data: Dict[str, Any],
    project_id: str,
    location: str,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Transform declarative YAML into Vertex AI / Agent Platform v1beta1 REST API payload."""
    policy_id = policy_data["id"]
    payload: Dict[str, Any] = {
        "displayName": policy_data.get("displayName", policy_id),
        "description": policy_data.get("description", ""),
        "naturalLanguageConstraint": policy_data["naturalLanguageConstraint"].strip(),
    }

    if "agent" in policy_data:
        agent_val = policy_data["agent"]
        if isinstance(agent_val, str):
            agent_val = (
                agent_val.replace("<PROJECT_ID>", project_id)
                .replace("agentic-policies", project_id)
                .replace("<LOCATION>", location)
                .replace("us-central1", location)
            )
            effective_agent_id = (
                agent_id
                or os.environ.get("AGENT_REGISTRY_ID")
                or os.environ.get("AGENT_ID")
            )
            if effective_agent_id:
                agent_val = (
                    agent_val.replace("<AGENT_REGISTRY_ID>", effective_agent_id)
                    .replace("<AGENT_ID>", effective_agent_id)
                )
        payload["agent"] = agent_val

    if "mcpTools" in policy_data:
        payload["mcpTools"] = policy_data["mcpTools"]

    if "agentResponseCustomization" in policy_data:
        payload["agentResponseCustomization"] = policy_data["agentResponseCustomization"]

    return payload


def get_gcp_access_token() -> Optional[str]:
    """Retrieve Google Cloud OAuth access token using google-auth default credentials."""
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token
    except Exception as e:
        logger.warning(f"Could not automatically retrieve GCP access token: {e}")
        return None


def deploy_policy(
    policy_path: Path,
    policy_data: Dict[str, Any],
    project_id: str,
    location: str,
    token: Optional[str] = None,
    dry_run: bool = False,
    agent_id: Optional[str] = None,
) -> bool:
    """Deploy or simulate deployment of a single Semantic Governance Policy."""
    policy_id = policy_data["id"]
    payload = build_api_payload(policy_data, project_id, location, agent_id=agent_id)

    print(f"\n============================================================")
    print(f"Policy ID:    {policy_id}")
    print(f"File:         {policy_path.name}")
    print(f"Display Name: {payload.get('displayName')}")
    print(f"Agent:        {payload.get('agent', 'All Agents')}")
    print(f"Resource URI: projects/{project_id}/locations/{location}/semanticGovernancePolicies/{policy_id}")
    print(f"============================================================")

    if dry_run:
        print("[DRY-RUN] Validation passed. Payload preview:")
        print(json.dumps(payload, indent=2))
        return True

    if not token:
        logger.error(
            f"Deployment failed for {policy_id}: No GCP credentials available. "
            f"Run 'gcloud auth application-default login' or use --dry-run."
        )
        return False

    base_url = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{location}/semanticGovernancePolicies"
    resource_url = f"{base_url}/{policy_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            logger.info(f"Checking existing status for policy '{policy_id}'...")
            check_resp = client.get(resource_url, headers=headers)

            if check_resp.status_code == 200:
                logger.info(f"Policy '{policy_id}' exists. Updating (PATCH)...")
                mask = "displayName,description,naturalLanguageConstraint,agentResponseCustomization"
                update_url = f"{resource_url}?updateMask={mask}"
                update_resp = client.patch(update_url, headers=headers, json=payload)
                if update_resp.status_code in (200, 201):
                    logger.info(f"Successfully updated policy '{policy_id}'.")
                    return True
                else:
                    logger.error(f"Failed to update policy '{policy_id}': {update_resp.status_code} - {update_resp.text}")
                    return False
            elif check_resp.status_code == 404:
                logger.info(f"Policy '{policy_id}' not found. Creating (POST)...")
                create_url = f"{base_url}?semanticGovernancePolicyId={policy_id}"
                create_resp = client.post(create_url, headers=headers, json=payload)
                if create_resp.status_code in (200, 201):
                    logger.info(f"Successfully created policy '{policy_id}'.")
                    return True
                else:
                    logger.error(f"Failed to create policy '{policy_id}': {create_resp.status_code} - {create_resp.text}")
                    return False
            else:
                logger.error(f"Failed checking policy '{policy_id}': {check_resp.status_code} - {check_resp.text}")
                return False

    except Exception as e:
        logger.error(f"Network error deploying policy '{policy_id}': {e}")
        return False


def main() -> int:
    default_region = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
    default_project = os.environ.get("GOOGLE_CLOUD_PROJECT")

    parser = argparse.ArgumentParser(
        description="Deploy declarative Semantic Governance Policies to Vertex AI / Agent Platform."
    )
    parser.add_argument(
        "--project",
        default=default_project,
        help="Google Cloud Project ID",
    )
    parser.add_argument(
        "--location",
        default=default_region,
        help=f"Google Cloud Region (default: {default_region})",
    )
    parser.add_argument(
        "--policy-dir",
        default=str(Path(__file__).parent if (Path(__file__).parent / "semantic_data_access_policy.yaml").exists() else Path("policies")),
        help="Path to directory containing policy YAML files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate YAML policies and preview payloads without calling Google Cloud APIs",
    )
    parser.add_argument(
        "--agent-id",
        "--agent-registry-id",
        default=os.environ.get("AGENT_REGISTRY_ID") or os.environ.get("AGENT_ID"),
        help="Target Agent Registry agent resource ID to replace <AGENT_REGISTRY_ID>",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output",
    )

    args = parser.parse_args()

    if not args.project:
        parser.error("--project or GOOGLE_CLOUD_PROJECT environment variable is required.")

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    policy_dir = Path(args.policy_dir)
    logger.info(f"Scanning for Semantic Governance Policies in: {policy_dir.resolve()}")

    try:
        policies = load_all_policies(policy_dir)
    except Exception as e:
        logger.error(f"Failed scanning policy directory: {e}")
        return 1

    if not policies:
        logger.warning(f"No policy YAML files found in {policy_dir.resolve()}")
        return 0

    logger.info(f"Found {len(policies)} policies to process.")

    token = None
    agent_id = args.agent_id
    if not args.dry_run:
        logger.info(f"Target Project: {args.project} | Region: {args.location}")
        token = get_gcp_access_token()
        if not token:
            logger.warning("Unable to obtain GCP credentials. Tip: use --dry-run for local validation.")
        elif not agent_id:
            discovered = resolve_agent_registry_id(args.project, args.location, token)
            if discovered:
                logger.info(f"Auto-discovered Agent Registry resource: {discovered}")
                agent_id = discovered

    success_count = 0
    for path, data in policies:
        ok = deploy_policy(
            policy_path=path,
            policy_data=data,
            project_id=args.project,
            location=args.location,
            token=token,
            dry_run=args.dry_run,
            agent_id=agent_id,
        )
        if ok:
            success_count += 1

    print("\n------------------------------------------------------------")
    print(f"Summary: {success_count}/{len(policies)} policies processed successfully.")
    print("------------------------------------------------------------")

    return 0 if success_count == len(policies) else 1


if __name__ == "__main__":
    sys.exit(main())
