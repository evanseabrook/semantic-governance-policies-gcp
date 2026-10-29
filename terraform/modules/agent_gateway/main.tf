data "google_project" "project" {
  project_id = var.project_id
}

resource "google_network_services_agent_connectivity_template" "template" {
  agent_connectivity_template_id = var.connectivity_template_id
  location                       = var.region
  project                        = var.project_id
  description                    = "Agent Connectivity Template for Agent Gateway egress"
  labels                         = var.labels

  access_path = "AGENT_TO_ANYWHERE"

  egress_network_config {
    network_attachment = var.network_attachment_id

    dns_peering_config {
      domains        = ["agent.internal."]
      target_network = "projects/${var.project_id}/global/networks/${var.network_name}"
    }
  }
}

resource "google_network_services_agent_gateway" "gateway" {
  name        = var.gateway_name
  location    = var.region
  project     = var.project_id
  description = "Managed Agent Gateway for customer policy agent governing MCP tool invocations"
  labels      = var.labels

  google_managed {
    governed_access_path = "AGENT_TO_ANYWHERE"
  }

  agent_connectivity_template = "projects/${data.google_project.project.number}/locations/${var.region}/agentConnectivityTemplates/${google_network_services_agent_connectivity_template.template.agent_connectivity_template_id}"

  registries = [
    "//agentregistry.googleapis.com/projects/${var.project_id}/locations/${var.region}"
  ]

  depends_on = [google_network_services_agent_connectivity_template.template]
}
