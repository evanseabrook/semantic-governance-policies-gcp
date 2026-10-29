output "network_id" {
  description = "The ID of the VPC network"
  value       = google_compute_network.network.id
}

output "network_name" {
  description = "The name of the VPC network"
  value       = google_compute_network.network.name
}

output "subnetwork_id" {
  description = "The ID of the subnetwork"
  value       = google_compute_subnetwork.subnetwork.id
}

output "subnetwork_name" {
  description = "The name of the subnetwork"
  value       = google_compute_subnetwork.subnetwork.name
}

output "sgp_subnetwork_id" {
  description = "The ID of the SGP subnetwork"
  value       = google_compute_subnetwork.sgp_subnetwork.id
}

output "sgp_subnetwork_name" {
  description = "The name of the SGP subnetwork"
  value       = google_compute_subnetwork.sgp_subnetwork.name
}

output "network_attachment_id" {
  description = "The ID of the Compute Network Attachment"
  value       = google_compute_network_attachment.attachment.id
}

output "network_attachment_name" {
  description = "The name of the Compute Network Attachment"
  value       = google_compute_network_attachment.attachment.name
}
