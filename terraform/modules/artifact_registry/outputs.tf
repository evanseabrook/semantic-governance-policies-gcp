output "repository_id" {
  description = "The ID of the created Artifact Registry repository"
  value       = google_artifact_registry_repository.mcp_repo.repository_id
}

output "repository_url" {
  description = "The Docker image base URL for the repository"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.mcp_repo.repository_id}"
}
