"""CLI utility to query and test prompts against a deployed Vertex AI Agent Engine."""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is prioritized in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
agent_dir = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] == agent_dir:
    sys.path.pop(0)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import vertexai
from vertexai import agent_engines

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent.query")


def query_deployed_agent(
    prompt: str,
    project_id: Optional[str] = None,
    location: str = "us-central1",
    display_name: str = "customer-policy-agent",
    user_id: str = "test-user",
    session_id: str = None,
):
    """Query a deployed ADK Agent on Vertex AI Agent Engine."""
    effective_project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    logger.info(f"Connecting to Vertex AI in project '{effective_project}' ({location})...")
    vertexai.init(project=effective_project, location=location)

    logger.info(f"Looking for deployed agent with display_name='{display_name}'...")
    matched = [eng for eng in agent_engines.list() if eng.display_name == display_name]
    if not matched:
        raise RuntimeError(
            f"No deployed agent found with display_name='{display_name}' in project '{project_id}'."
        )

    # Pick the most recently updated or created agent
    engine = sorted(
        matched,
        key=lambda e: (
            getattr(e.gca_resource, "update_time", None)
            or getattr(e.gca_resource, "create_time", None)
        ),
        reverse=True,
    )[0]

    logger.info(f"Found Agent Engine: {engine.resource_name}")
    print(f"\n=======================================================")
    print(f"Agent: {engine.display_name} ({engine.resource_name})")
    print(f"Prompt: {prompt}")
    print(f"=======================================================\n")

    response_stream = engine.stream_query(
        message=prompt,
        user_id=user_id,
        session_id=session_id,
    )

    print("--- Agent Response ---")
    for event in response_stream:
        # Event can be an event dict or model chunk
        if isinstance(event, dict):
            # Print content or event
            content = event.get("content") or event.get("text") or event
            print(content, flush=True)
        else:
            print(event, flush=True)
    print("\n----------------------", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Query deployed ADK Agent on Vertex AI Agent Engine")
    parser.add_argument(
        "--prompt",
        "-p",
        default="What tools do you have access to?",
        help="Prompt message to send to the agent",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        help="GCP Project ID",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GOOGLE_CLOUD_REGION", "us-central1"),
        help="GCP Region",
    )
    parser.add_argument(
        "--display-name",
        default="customer-policy-agent",
        help="Display name of the deployed agent resource",
    )
    parser.add_argument(
        "--user-id",
        default="test-user-01",
        help="User ID for the session",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session ID",
    )

    args = parser.parse_args()
    query_deployed_agent(
        prompt=args.prompt,
        project_id=args.project,
        location=args.location,
        display_name=args.display_name,
        user_id=args.user_id,
        session_id=args.session_id,
    )


if __name__ == "__main__":
    main()
