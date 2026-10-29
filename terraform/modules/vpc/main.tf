resource "google_compute_network" "network" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  description             = "Custom VPC network for Agent Gateway private connectivity"
}

resource "google_compute_subnetwork" "subnetwork" {
  project                  = var.project_id
  name                     = var.subnetwork_name
  region                   = var.region
  network                  = google_compute_network.network.id
  ip_cidr_range            = var.ip_cidr_range
  private_ip_google_access = true
  description              = "Subnetwork for Agent Gateway PSC network attachment"
}

resource "google_compute_subnetwork" "sgp_subnetwork" {
  project                  = var.project_id
  name                     = "agent-sgp-subnetwork"
  region                   = var.region
  network                  = google_compute_network.network.id
  ip_cidr_range            = "10.11.12.0/24"
  private_ip_google_access = true
  description              = "Dedicated subnetwork for Semantic Governance Policy and Agent Gateway egress"
}

resource "google_compute_firewall" "allow_internal" {
  name        = "${var.network_name}-allow-internal"
  project     = var.project_id
  network     = google_compute_network.network.id
  description = "Allow internal traffic within the Agent VPC network"

  allow {
    protocol = "all"
  }

  source_ranges = [
    "10.11.12.0/24",
    var.ip_cidr_range,
  ]
}

resource "google_compute_network_attachment" "attachment" {
  project               = var.project_id
  name                  = var.network_attachment_name
  region                = var.region
  connection_preference = "ACCEPT_AUTOMATIC"

  subnetworks = [
    google_compute_subnetwork.sgp_subnetwork.id,
  ]

  description = "Network attachment for Agent Gateway egress connectivity"
}
