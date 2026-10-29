resource "google_artifact_registry_repository" "mcp_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "Docker repository for Cloud Run MCP Server container images"
  format        = "DOCKER"
}
