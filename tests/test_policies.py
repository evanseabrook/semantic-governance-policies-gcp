"""Unit tests for Semantic Governance Policies and the deployment script."""

from pathlib import Path
import pytest

from policies.deploy_policies import (
    build_api_payload,
    deploy_policy,
    load_all_policies,
    load_policy,
    validate_policy_schema,
)

POLICY_DIR = Path("policies")


def test_load_all_policies():
    policies = load_all_policies(POLICY_DIR)
    assert len(policies) == 2
    ids = {data["id"] for _, data in policies}
    expected = {
        "semantic-wire-fraud-coercion-policy",
        "semantic-account-overview-policy",
    }
    assert ids == expected


def test_policy_schema_validation():
    # Test valid policy
    sample_valid = {
        "id": "sample-policy",
        "displayName": "Sample Policy",
        "description": "Sample description",
        "agent": "projects/test-project/locations/us-central1/agents/agent-1234",
        "naturalLanguageConstraint": "Only execute if verified",
        "agentResponseCustomization": {"denialMessage": "Request denied"},
    }
    validate_policy_schema(sample_valid, Path("test.yaml"))

    # Test invalid id
    with pytest.raises(ValueError, match="must contain only lowercase letters"):
        invalid = dict(sample_valid, id="Invalid_ID_Uppercase")
        validate_policy_schema(invalid, Path("test.yaml"))

    # Test missing naturalLanguageConstraint
    with pytest.raises(ValueError, match="Missing or empty 'naturalLanguageConstraint'"):
        invalid = dict(sample_valid, naturalLanguageConstraint="")
        validate_policy_schema(invalid, Path("test.yaml"))

    # Test invalid agent format
    with pytest.raises(ValueError, match="'agent' must be a fully-qualified resource URI"):
        invalid = dict(sample_valid, agent="invalid-agent-id")
        validate_policy_schema(invalid, Path("test.yaml"))


def test_build_api_payload():
    policies = load_all_policies(POLICY_DIR)
    _, sample_policy = policies[0]
    payload = build_api_payload(sample_policy, project_id="test-project", location="us-central1")

    assert "displayName" in payload
    assert "naturalLanguageConstraint" in payload
    assert len(payload["naturalLanguageConstraint"]) > 0
    assert payload["agent"].startswith("projects/test-project/locations/us-central1/agents/")


def test_dry_run_deployment():
    policies = load_all_policies(POLICY_DIR)
    for path, data in policies:
        success = deploy_policy(
            policy_path=path,
            policy_data=data,
            project_id="test-project",
            location="us-central1",
            token=None,
            dry_run=True,
        )
        assert success is True
