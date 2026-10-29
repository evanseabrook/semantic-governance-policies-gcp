output "service_name" {
  description = "Name of the Cloud Run service"
  value       = google_cloud_run_v2_service.mcp_service.name
}

data "google_project" "project" {
  project_id = var.project_id
}

locals {
  canonical_url = "https://${google_cloud_run_v2_service.mcp_service.name}-${data.google_project.project.number}.${var.region}.run.app"
}

output "service_url" {
  description = "The HTTPS invocation URL of the Cloud Run service"
  value       = local.canonical_url
}

output "mcp_endpoint_url" {
  description = "The Streamable HTTP MCP endpoint URL"
  value       = "${local.canonical_url}/mcp"
}
