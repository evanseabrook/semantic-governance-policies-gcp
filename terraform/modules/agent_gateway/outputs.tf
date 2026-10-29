output "agent_gateway_id" {
  description = "The ID of the Agent Gateway resource"
  value       = google_network_services_agent_gateway.gateway.id
}

output "agent_gateway_name" {
  description = "The short name of the Agent Gateway"
  value       = google_network_services_agent_gateway.gateway.name
}

output "connectivity_template_id" {
  description = "The ID of the Agent Connectivity Template"
  value       = google_network_services_agent_connectivity_template.template.id
}
