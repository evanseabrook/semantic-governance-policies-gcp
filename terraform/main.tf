terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.8"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}


# Core Service APIs required for Cloud Run, Artifact Registry, Vertex AI, and Agent Platform
locals {
  services = var.enable_apis ? [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com",
    "cloudbuild.googleapis.com",
    "compute.googleapis.com",
    "dns.googleapis.com",
    "networkservices.googleapis.com",
    "networksecurity.googleapis.com",
    "apphub.googleapis.com",
    "agentregistry.googleapis.com",
    "iap.googleapis.com",
  ] : []
}

resource "google_project_service" "enabled_apis" {
  for_each                   = toset(local.services)
  project                    = var.project_id
  service                    = each.key
  disable_on_destroy         = false
  disable_dependent_services = false
}

# Module: Artifact Registry for Docker images
module "artifact_registry" {
  source     = "./modules/artifact_registry"
  project_id = var.project_id
  region     = var.region

  depends_on = [google_project_service.enabled_apis]
}

# Module: IAM Service Accounts and Permissions
module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id

  depends_on = [google_project_service.enabled_apis]
}

# Module: Cloud Run MCP Service
module "cloud_run_mcp" {
  source                = "./modules/cloud_run_mcp"
  project_id            = var.project_id
  region                = var.region
  container_image       = "${module.artifact_registry.repository_url}/customer-policy-mcp:${var.image_tag}"
  service_account_email = module.iam.mcp_server_sa_email
  invoker_sa_email      = module.iam.agent_engine_sa_email

  depends_on = [
    module.artifact_registry,
    module.iam,
    google_project_service.enabled_apis,
  ]
}

# Module: Agent Engine Storage and Configuration
module "agent_engine" {
  source                = "./modules/agent_engine"
  project_id            = var.project_id
  region                = var.region
  agent_engine_sa_email = module.iam.agent_engine_sa_email

  depends_on = [
    module.iam,
    google_project_service.enabled_apis,
  ]
}

# Module: VPC Networking and Network Attachment
module "vpc" {
  source     = "./modules/vpc"
  project_id = var.project_id
  region     = var.region

  depends_on = [google_project_service.enabled_apis]
}

# Module: Agent Gateway for Governance and Tool Invocations
module "agent_gateway" {
  source                = "./modules/agent_gateway"
  project_id            = var.project_id
  region                = var.region
  network_name          = module.vpc.network_name
  network_attachment_id = module.vpc.network_attachment_id

  depends_on = [
    module.vpc,
    google_project_service.enabled_apis,
  ]
}


