# Convenience Makefile for policy-fun project
SHELL := /bin/bash
PROJECT_ID ?= $(GOOGLE_CLOUD_PROJECT)
REGION ?= us-central1
IMAGE_TAG ?= latest
REPO_NAME ?= customer-mcp-repo
IMAGE_NAME = $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(REPO_NAME)/customer-policy-mcp:$(IMAGE_TAG)

.PHONY: help check-project install dev test tf-init tf-plan tf-apply build-image deploy-policies deploy-policies-dry-run deploy-agent deploy-agent-dry-run query-agent clean

check-project:
ifeq ($(strip $(PROJECT_ID)),)
	$(error PROJECT_ID is required. Pass PROJECT_ID=<project-id> (e.g. make deploy-policies PROJECT_ID=my-project-id) or export GOOGLE_CLOUD_PROJECT=<project-id>)
endif

help:
	@echo "Available targets:"
	@echo "  make install                 - Sync python dependencies using uv"
	@echo "  make dev                     - Run local MCP server on http://localhost:8080/mcp"
	@echo "  make test                    - Run pytest test suite"
	@echo "  make tf-init                 - Initialize Terraform"
	@echo "  make tf-plan                 - Plan Terraform infrastructure"
	@echo "  make tf-apply                - Apply Terraform infrastructure"
	@echo "  make build-image             - Build and submit MCP container image via Cloud Build"
	@echo "  make register-mcp            - Register Cloud Run MCP server & tools with Agent Registry"
	@echo "  make register-mcp-dry-run    - Preview Agent Registry MCP registration payload"
	@echo "  make deploy-policies         - Deploy Semantic Governance policies to Agent Gateway"
	@echo "  make deploy-policies-dry-run - Validate Semantic Governance policies locally (dry-run)"
	@echo "  make deploy-agent            - Package and deploy ADK agent to Vertex AI Agent Engine"
	@echo "  make deploy-agent-dry-run    - Validate ADK agent packaging locally (dry-run)"
	@echo "  make query-agent             - Send a prompt to the deployed agent (e.g. PROMPT=\"hello\")"

install:
	uv sync

dev:
	uv run python -m uvicorn mcp_server.server:app --host 0.0.0.0 --port 8080 --reload

test:
	uv run pytest -v

tf-init:
	terraform -chdir=terraform init

tf-plan:
	terraform -chdir=terraform plan

tf-apply:
	terraform -chdir=terraform apply

build-image: check-project
	@echo "Submitting build to Google Cloud Build for image: $(IMAGE_NAME)"
	gcloud builds submit mcp_server --tag $(IMAGE_NAME) --project $(PROJECT_ID)

register-mcp: check-project
	@echo "Registering MCP Server & Tools to Agent Registry for project $(PROJECT_ID)..."
	uv run python mcp_server/register.py --project $(PROJECT_ID) --location $(REGION)

register-mcp-dry-run: check-project
	@echo "Previewing MCP Server registration payload for project $(PROJECT_ID)..."
	uv run python mcp_server/register.py --project $(PROJECT_ID) --location $(REGION) --dry-run

deploy-policies: check-project
	@echo "Deploying Semantic Governance Policies for project $(PROJECT_ID)..."
	uv run python policies/deploy_policies.py --project $(PROJECT_ID) --location $(REGION)

deploy-policies-dry-run: check-project
	@echo "Validating Semantic Governance Policies in dry-run mode for project $(PROJECT_ID)..."
	uv run python policies/deploy_policies.py --project $(PROJECT_ID) --location $(REGION) --dry-run

deploy-agent: check-project
	@echo "Deploying ADK Agent to Vertex AI Agent Engine for project $(PROJECT_ID)..."
	eval "$$(terraform -chdir=terraform output -raw agent_deploy_command 2>/dev/null || echo 'uv run --env-file opentelemetry.env python agent/deploy.py --project $(PROJECT_ID) --location $(REGION) --staging-bucket gs://$(PROJECT_ID)-agent-engine-staging')"

deploy-agent-dry-run: check-project
	@echo "Validating ADK Agent packaging in dry-run mode for project $(PROJECT_ID)..."
	uv run --env-file opentelemetry.env python agent/deploy.py --project $(PROJECT_ID) --location $(REGION) --mcp-server-name customer-banking-mcp --dry-run

query-agent: check-project
	@echo "Querying ADK Agent for project $(PROJECT_ID)..."
	uv run python agent/query.py --project $(PROJECT_ID) --location $(REGION) $(if $(PROMPT),--prompt "$(PROMPT)",)

