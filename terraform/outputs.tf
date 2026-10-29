output "project_id" {
  description = "Google Cloud Project ID"
  value       = var.project_id
}

output "region" {
  description = "Google Cloud Region"
  value       = var.region
}

output "artifact_registry_repo" {
  description = "Artifact Registry Docker repository URL"
  value       = module.artifact_registry.repository_url
}

output "cloud_run_service_url" {
  description = "Base URL of the Cloud Run MCP service"
  value       = module.cloud_run_mcp.service_url
}

output "cloud_run_mcp_endpoint" {
  description = "Streamable HTTP MCP tool endpoint URL"
  value       = module.cloud_run_mcp.mcp_endpoint_url
}

output "mcp_server_sa_email" {
  description = "Service Account email for Cloud Run MCP Server"
  value       = module.iam.mcp_server_sa_email
}

output "agent_engine_sa_email" {
  description = "Service Account email for Vertex AI Agent Engine"
  value       = module.iam.agent_engine_sa_email
}

output "staging_bucket_url" {
  description = "GCS bucket for Agent Engine deployment staging"
  value       = module.agent_engine.staging_bucket_url
}

output "agent_deploy_command" {
  description = "Command to package and deploy ADK Agent to Vertex AI Agent Engine"
  value       = "uv run --env-file opentelemetry.env python agent/deploy.py --project ${var.project_id} --location ${var.region} --staging-bucket ${module.agent_engine.staging_bucket_url} --mcp-server-name customer-banking-mcp --gateway-url ${module.cloud_run_mcp.mcp_endpoint_url}"
}

output "policy_deploy_command" {
  description = "Command to deploy Semantic Governance Policies to Agent Gateway"
  value       = "uv run python policies/deploy_policies.py --project ${var.project_id} --location ${var.region}"
}

output "agent_gateway_id" {
  description = "The ID of the Agent Gateway resource"
  value       = module.agent_gateway.agent_gateway_id
}

output "agent_gateway_name" {
  description = "The name of the Agent Gateway"
  value       = module.agent_gateway.agent_gateway_name
}

output "agent_network_id" {
  description = "The ID of the VPC network supporting the Agent Gateway"
  value       = module.vpc.network_id
}

output "agent_network_attachment_id" {
  description = "The ID of the Compute Network Attachment for Agent Gateway egress"
  value       = module.vpc.network_attachment_id
}

output "sgp_subnetwork_id" {
  description = "The ID of the dedicated SGP subnetwork"
  value       = module.vpc.sgp_subnetwork_id
}

output "sgp_subnetwork_name" {
  description = "The name of the dedicated SGP subnetwork"
  value       = module.vpc.sgp_subnetwork_name
}


