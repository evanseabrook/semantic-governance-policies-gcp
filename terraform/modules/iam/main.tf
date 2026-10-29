# Service Account for Cloud Run MCP Server
resource "google_service_account" "mcp_server_sa" {
  project      = var.project_id
  account_id   = "mcp-server-sa"
  display_name = "Cloud Run MCP Server Identity"
}

# Service Account for Vertex AI Agent Engine
resource "google_service_account" "agent_engine_sa" {
  project      = var.project_id
  account_id   = "agent-engine-sa"
  display_name = "Vertex AI Agent Engine Identity"
}

# Grant Agent Engine SA permission to invoke Vertex AI Platform APIs
resource "google_project_iam_member" "agent_engine_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_engine_sa.email}"
}

# Grant Logging and Monitoring to both identities
resource "google_project_iam_member" "mcp_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.mcp_server_sa.email}"
}

resource "google_project_iam_member" "agent_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_engine_sa.email}"
}
