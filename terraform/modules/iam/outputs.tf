output "mcp_server_sa_email" {
  description = "Email of the MCP Server service account"
  value       = google_service_account.mcp_server_sa.email
}

output "agent_engine_sa_email" {
  description = "Email of the Agent Engine service account"
  value       = google_service_account.agent_engine_sa.email
}
