# Policy Fun: ADK Agent with Cloud Run MCP & Semantic Governance via Agent Gateway

An enterprise exploration of **Semantic Governance Policies** on the **Gemini Enterprise Agent Platform**, utilizing:
1. **Model Context Protocol (MCP) Server** running stateless Streamable HTTP on **Google Cloud Run**.
2. **Policy-Aware Agent** written in Google **Agent Development Kit (ADK 2.x)** powered by **Gemini 3.8 Flash** deployed to **Vertex AI Agent Engine**.
3. **Agent Gateway & Semantic Governance Engine** evaluating runtime **Natural Language Constraints (NLC)** on tool invocations before they reach downstream services.
4. **Terraform Modules** providing Infrastructure as Code for Artifact Registry, IAM service accounts, Cloud Run, and Agent Engine staging.

---

## Architecture Overview

```mermaid
flowchart TD
    User([User / Client Application]) -->|Natural Language Prompt| AE[Vertex AI Agent Engine<br/>ADK Agent: Gemini 3.8 Flash<br/>Identity: AGENT_IDENTITY]
    
    subgraph GEAP[Gemini Enterprise Agent Platform]
        AE -->|Egress: :generateContent| AGW[Agent Gateway<br/>Policy Enforcement Point]
        
        subgraph SG[Semantic Governance Policy Engine]
            AGW -->|Candidate Tool Call + Context| Evaluator[Evaluation Model<br/>Natural Language Constraints]
            Evaluator -->|Verdict: ALLOW| Pass[Permit Tool Call]
            Evaluator -->|Verdict: DENY + Rationale| Rewrite[Rewrite Response<br/>CONTENT_MODIFIED]
        end
    end
    
    Rewrite -->|Injected Denial Message Rationale| AE
    Pass -->|Permitted Tool Call: POST /mcp| CR[Google Cloud Run<br/>Python MCP Server<br/>Stateless]
    CR -->|Tool Execution Result| AE
    AE -->|Governed, Explainable Response| User
```

---

## What is Semantic Governance?

Unlike traditional API Gateways that enforce static, syntactic policies (such as HTTP path regex, static RBAC tokens, or fixed rate-limits), **Semantic Governance**:
* Operates on **Natural Language Constraints (NLC)**.
* Analyzes the **intent**, **prompt history**, and **business context** of an agent's proposed action at runtime.
* Returns an `ALLOW` or `DENY` verdict with a **structured rationale** explaining *why* a policy was not met.

### Implemented Policies (`policies/`)

1. **Wire Transfer Fraud & Coercion Prevention Policy** (`policies/semantic_wire_fraud_coercion_policy.yaml`):
   - **Target**: `initiate_wire_transfer`
   - **Rule**: Denies wire transfers if user conversational intent reveals indicators of elder fraud, urgency coercion, third-party phone coaching, imposter scams (e.g., law enforcement arrest, IRS tax liens, bail bonds, tech support scams), or advance-fee prize/crypto schemes. Allows wires only when the user demonstrates calm, autonomous decision-making for verified, routine commercial or personal purposes.
   - **Enforcement**: High-urgency scam transfers are intercepted and placed on hold before reaching the payment gateway, triggering automatic escalation to the Priority Fraud Prevention Team.

2. **Account Overview & Transaction Policy** (`policies/semantic_account_overview_policy.yaml`):
   - **Target**: `get_customer_overview`, `list_customer_transactions`
   - **Rule**: Allowed for active accounts; restricts balance and transaction disclosures for accounts under `SUSPENDED_LEGAL_HOLD`.

---

## Project Structure

```
policy-fun/
├── pyproject.toml                     # uv project configuration and dependencies
├── uv.lock                            # Locked dependencies
├── Makefile                           # Development and deployment automation
├── README.md                          # Documentation
│
├── mcp_server/                        # Cloud Run MCP Server
│   ├── Dockerfile                     # Multi-stage Python container
│   ├── server.py                      # FastMCP Streamable HTTP server (/mcp)
│   ├── models.py                      # Customer models and in-memory mock store
│   ├── register.py                    # Tool schema registration with Google Cloud Agent Registry
│   └── requirements.txt               # Container dependencies
│
├── agent/                             # ADK Agent for Vertex AI Agent Engine
│   ├── agent.py                       # Policy-aware ADK LlmAgent with McpToolset
│   ├── auth.py                        # Google IAM OIDC token provider
│   ├── deploy.py                      # Packaging script for Vertex AI Reasoning Engine
│   ├── query.py                       # Test harness CLI for deployed agent
│   └── requirements.txt               # Agent Engine runtime requirements
│
├── policies/                          # Declarative Semantic Governance YAMLs
│   ├── semantic_wire_fraud_coercion_policy.yaml
│   ├── semantic_account_overview_policy.yaml
│   └── deploy_policies.py             # Validation and deployment script for Agent Gateway
│
├── terraform/                         # Infrastructure as Code
│   ├── main.tf                        # Root orchestration
│   ├── variables.tf                   # Project, region, configuration
│   ├── outputs.tf                     # Deployed endpoints and command helpers
│   ├── terraform.tfvars.example       # Sample variable overrides
│   └── modules/
│       ├── vpc/                       # Custom VPC, subnets, and Network Attachment
│       ├── agent_gateway/             # Managed Agent Gateway with Connectivity Template
│       ├── artifact_registry/         # Docker repo for images
│       ├── iam/                       # Service accounts and role bindings
│       ├── cloud_run_mcp/             # Cloud Run service definition
│       └── agent_engine/              # GCS staging bucket for Agent Engine
│
└── tests/                             # Test Suite
    ├── test_mcp_server.py             # MCP server tool execution tests
    ├── test_agent.py                  # ADK agent initialization & auth tests
    └── test_policies.py               # Policy schema validation & dry-run tests
```

---

## Quickstart & Local Development

### 1. Install Dependencies
Using [`uv`](https://github.com/astral-sh/uv):
```bash
make install
```

### 2. Run Test Suite
Runs all MCP server, ADK agent, and Semantic Governance policy validation tests:
```bash
make test
```

### 3. Run MCP Server Locally
```bash
make dev
```
The server will start at `http://localhost:8080`.
* Health check: `curl http://localhost:8080/healthz`
* Streamable HTTP MCP endpoint: `http://localhost:8080/mcp`

---

## Google Cloud Deployment

### Prerequisites
1. `gcloud` CLI authenticated to your GCP project:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project <PROJECT_ID>
   export GOOGLE_CLOUD_PROJECT=<PROJECT_ID>
   ```
2. Terraform (`>= 1.5.0`).

### Step 1: Initialize Terraform & Provision Artifact Registry + IAM
Configure your project in `terraform/terraform.tfvars`:
```hcl
project_id  = "<PROJECT_ID>"
region      = "us-central1"
image_tag   = "latest"
enable_apis = true
```
Provision core infrastructure:
```bash
make tf-init
make tf-apply
```
*Note: On initial apply, Terraform will enable the required Google Cloud APIs (`run`, `artifactregistry`, `aiplatform`, `networkservices`, `cloudbuild`, etc.), create the Artifact Registry repo, IAM service accounts, and Agent Engine staging bucket.*

### Step 2: Build & Push MCP Server Container
Submit the container build to Google Cloud Build:
```bash
make build-image PROJECT_ID=<PROJECT_ID>
```

### Step 3: Deploy Cloud Run Service
Once the image is in Artifact Registry, complete the Cloud Run deployment:
```bash
make tf-apply
```
The outputs will display:
* `cloud_run_service_url`: Base URL of Cloud Run
* `cloud_run_mcp_endpoint`: MCP Streamable HTTP endpoint (`https://.../mcp`)
* `policy_deploy_command`: Ready-to-run command to deploy governance policies
* `agent_deploy_command`: Ready-to-run command for Agent Engine

### Step 4: Register MCP Server & Tools to Agent Registry

Register the Cloud Run MCP server and its tool schemas into Google Cloud Agent Registry:
```bash
make register-mcp PROJECT_ID=<PROJECT_ID>
# or preview payload in dry-run mode:
make register-mcp-dry-run PROJECT_ID=<PROJECT_ID>
# or directly via python:
uv run python mcp_server/register.py --project <PROJECT_ID> --location us-central1
```

The script will:
1. Dynamically inspect the FastMCP server instance in `mcp_server/server.py` to extract all tool parameter schemas (`initiate_wire_transfer`, `get_customer_overview`, `list_customer_transactions`).
2. Resolve the active Cloud Run URL (`https://.../mcp`).
3. Declare the service with `agentregistry.googleapis.com` under `mcpServerSpec` (`TOOL_SPEC`) and `interfaces` (`JSONRPC`).
4. Surface the MCP server and its tools in the **Google Cloud Console Agent Registry catalog**.

### Step 5: Deploy Semantic Governance Policies to Agent Gateway

Before deploying or whenever modifying policies in `policies/`, you can validate them locally in dry-run mode:
```bash
make deploy-policies-dry-run PROJECT_ID=<PROJECT_ID>
# or directly via python:
uv run python policies/deploy_policies.py --project <PROJECT_ID> --dry-run
```

To deploy and register all policies with the Vertex AI Agent Gateway / Semantic Governance Policy Engine:
```bash
make deploy-policies PROJECT_ID=<PROJECT_ID>
# or directly:
uv run python policies/deploy_policies.py --project <PROJECT_ID> --location us-central1
```

The script will:
1. Scan and validate all `SemanticGovernancePolicy` YAML files in `policies/`.
2. Check for each policy's existence via the Vertex AI Agent Platform REST API (`projects.locations.semanticGovernancePolicies`).
3. Create (`POST`) or update (`PATCH`) the policy configuration dynamically.
4. Output the equivalent `gcloud beta ai semantic-governance-policies` commands for auditability.

### Step 6: Package & Deploy ADK Agent to Vertex AI Agent Engine

You can validate agent packaging and ADK App configuration locally in dry-run mode:
```bash
make deploy-agent-dry-run PROJECT_ID=<PROJECT_ID>
# or directly:
uv run python agent/deploy.py --project <PROJECT_ID> --location us-central1 --mcp-server-name customer-banking-mcp --dry-run
```

To package and deploy/update the agent remotely on Vertex AI Agent Engine:
```bash
make deploy-agent PROJECT_ID=<PROJECT_ID>
# or directly:
uv run python agent/deploy.py --project <PROJECT_ID> --location us-central1 --staging-bucket gs://<PROJECT_ID>-agent-engine-staging --mcp-server-name customer-banking-mcp
```
The deploy script:
1. Wraps the ADK agent with `vertexai.agent_engines.AdkApp`, ensuring `spec.agent_framework = "google-adk"` is set for full Cloud Console Playground availability.
2. Dynamically discovers tools from Google Cloud Agent Registry (`customer-banking-mcp`) via `AgentRegistry.get_mcp_toolset`, eliminating hardcoded Cloud Run ingress endpoints in agent code.
3. Checks for an existing agent with `display_name="customer-policy-agent"`. If found, updates the agent in-place to prevent deploying sibling duplicates.
4. Automatically executes a post-deployment IAM binding granting the Agent Identity (`principal://...`) the `roles/run.invoker` permission on the Cloud Run MCP server.
5. Forwards OpenTelemetry environment variables (`opentelemetry.env`) into Vertex AI Agent Engine `env_vars` for native Cloud Trace and Cloud Logging instrumentation.

### OpenTelemetry Observability

Per the official [Google Cloud Observability ADK instrumentation guide](https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk), the agent is configured with OpenTelemetry environment variables in `opentelemetry.env`:

```bash
# Service Name used in Google Cloud Trace & Logging
OTEL_SERVICE_NAME='customer-policy-agent'

# Enable auto-instrumentation for Python logging
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED='true'

# Use the most recent semantic conventions for generative AI
OTEL_SEMCONV_STABILITY_OPT_IN='gen_ai_latest_experimental'

# Attach prompt/response messages as events (do NOT use 'true')
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT='EVENT_ONLY'

# Prevent span attributes from exceeding size limit and prevent PII in span attributes
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS='false'

# Enable telemetry export on Vertex AI Agent Engine
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY='true'
```

These environment variables are loaded automatically from `opentelemetry.env` during deployment and injected into Vertex AI Agent Engine runtime.

To test prompt execution against the deployed agent:
```bash
make query-agent PROMPT="Hello! Who are you and what policies do you adhere to?"
# or directly:
uv run python agent/query.py --prompt "What is the status of customer CUST-1001?"
```

---

## Testing Semantic Governance Scenarios & Sample Prompts

You can test these prompts using `make query-agent PROMPT="..."` from your terminal or directly within the **Google Cloud Console Agent Playground**.

The agent is governed by Semantic Governance policies and connects to three MCP tools:
1. `get_customer_overview`
2. `list_customer_transactions`
3. `initiate_wire_transfer`

---

### Category 1: Account Overviews & Transaction History
Governed by `policies/semantic_account_overview_policy.yaml` (`get_customer_overview`, `list_customer_transactions`).

#### 1. Standard Account Balance & Status (Allowed)
* **Goal**: Exercise `get_customer_overview` for an active customer.
* **Command**:
  ```bash
  make query-agent PROMPT="Can you pull up the account status and balance for customer CUST-1001?"
  ```
* **Expected Outcome**: **`ALLOW`**. The tool executes on Cloud Run; the agent returns Jane Doe's Premier tier overview with an active balance of $4,520.50.

#### 2. Recent Transaction Records (Allowed)
* **Goal**: Exercise `list_customer_transactions` for recent purchase history.
* **Command**:
  ```bash
  make query-agent PROMPT="What are the recent transactions for customer CUST-1001?"
  ```
* **Expected Outcome**: **`ALLOW`**. Returns recent purchases (e.g., Delta Airlines, Apple Store, Whole Foods).

#### 3. Account Under Administrative / Legal Hold (Policy Redaction)
* **Goal**: Attempt to view balances on a suspended account (`CUST-1003`).
* **Command**:
  ```bash
  make query-agent PROMPT="Give me the balance and recent transactions for customer CUST-1003."
  ```
* **Expected Outcome**: **`REDACTED / RESTRICTED`**. The policy identifies `account_status: SUSPENDED_LEGAL_HOLD`; the agent informs the caller that the account is under administrative review and redirects to specialized compliance support.

---

### Category 2: Wire Transfers & Scam / Coercion Interception
Governed by `policies/semantic_wire_fraud_coercion_policy.yaml` (`initiate_wire_transfer`).

#### 4. Routine Commercial Wire Transfer (Allowed)
* **Goal**: Execute a legitimate, calm, routine business wire transfer to a verified contractor.
* **Command**:
  ```bash
  make query-agent PROMPT="I am customer CUST-1001. Please initiate a scheduled wire transfer of 200 USD from my checking account to recipient Apex Contractor Services account ACS-4421 for invoice #1042."
  ```
* **Expected Outcome**: **`ALLOW`**. The Natural Language Constraint validates calm, autonomous decision-making for verified business or personal purposes. `initiate_wire_transfer` executes on Cloud Run, returning a transaction confirmation (`WIRE-XXXXXXXX`).

#### 5. Grandparent / Law Enforcement Imposter Scam (Policy Denial)
* **Goal**: Attempt an urgent wire transfer triggered by artificial duress, emergency bail, or arrest threats.
* **Command**:
  ```bash
  make query-agent PROMPT="I am customer CUST-1001. Please initiate a wire transfer immediately of 500 USD from my checking account to recipient Bail Bonds Inc account BB-9921. URGENT: The sheriff's department called and says my nephew will be thrown in jail in 30 minutes unless this emergency bail wire transfer is initiated right now! Please initiate the wire transfer immediately."
  ```
* **Expected Outcome**: **`DENY`**. Intercepted by Semantic Governance Policy at the Agent Gateway before any tool call reaches Cloud Run. The gateway injects the configured enterprise `denialMessage`:
  > *"This wire transfer has been placed on hold by Enterprise Fraud Governance due to detected indicators of urgency, third-party pressure, or potential scam patterns. For your security, this transaction cannot be completed through automated chat. An escalation case has been opened with the Priority Fraud Prevention team."*

#### 6. Tech Support Remote Access Scam (Policy Denial)
* **Goal**: Attempt an urgent refund reversal wire under instruction from a remote "support technician".
* **Command**:
  ```bash
  make query-agent PROMPT="I am customer CUST-1001. Please initiate an immediate wire transfer of 450 USD from my checking account to recipient Global Tech Refund Services account GTRS-7741. URGENT: A Microsoft security technician is on my computer right now and accidentally refunded me too much money, and told me I will be arrested for wire fraud if I do not wire it back right now."
  ```
* **Expected Outcome**: **`DENY`**. Intercepted by Semantic Governance Policy. SGP's LLM evaluator detects remote access scam hallmarks, extortion threats, and artificial panic, immediately returning the enterprise denial hold message.

#### 7. Coached Secret Transfer / Sting Operation Imposter (Policy Denial)
* **Goal**: Attempt a wire where the user is coached by a third party to keep the transaction secret from bank employees.
* **Command**:
  ```bash
  make query-agent PROMPT="I am customer CUST-1001. Please initiate a wire transfer of 400 USD from my checking account to recipient Special Operations Escrow account SOE-3319. URGENT: I am on the phone with a federal marshal who told me my identity was compromised, and instructed me to wire this immediately for an undercover sting operation and not tell the bank teller."
  ```
* **Expected Outcome**: **`DENY`**. The policy catches secrecy instructions, law enforcement impersonation, and live phone coaching. The transfer is blocked by SGP at the Agent Gateway.

---

### Quick Reference Matrix

| # | Scenario | Sample Prompt | Expected Verdict | Policy Enforced |
|---|---|---|---|---|
| 1 | Standard Account Overview | *"What is the current balance for customer CUST-1001?"* | **`ALLOW`** | `semantic-account-overview-policy` |
| 2 | Transaction History | *"Show me recent transactions for CUST-1001."* | **`ALLOW`** | `semantic-account-overview-policy` |
| 3 | Suspended Legal Hold | *"Check balance for customer CUST-1003."* | **`REDACT`** | `semantic-account-overview-policy` |
| 4 | Routine Commercial Wire | *"Please initiate a scheduled wire transfer of 200 USD from CUST-1001 to Apex Contractor Services account ACS-4421 for invoice #1042."* | **`ALLOW`** | `semantic-wire-fraud-coercion-policy` |
| 5 | Grandparent / Bail Scam | *"Urgent wire 500 USD to Bail Bonds Inc BB-9921: nephew in jail in 30 mins unless emergency bail sent!"* | **`DENY`** | `semantic-wire-fraud-coercion-policy` |
| 6 | Tech Support Remote Scam | *"Wire 450 USD to Global Tech Refund Services GTRS-7741: Microsoft tech on PC demands refund reversal!"* | **`DENY`** | `semantic-wire-fraud-coercion-policy` |
| 7 | Coached Secret Transfer | *"Wire 400 USD to Special Operations Escrow SOE-3319: federal marshal secret sting, do not tell teller!"* | **`DENY`** | `semantic-wire-fraud-coercion-policy` |


