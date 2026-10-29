variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region for the subnetwork and network attachment"
  type        = string
}

variable "network_name" {
  description = "Name of the custom VPC network"
  type        = string
  default     = "agent-network"
}

variable "subnetwork_name" {
  description = "Name of the subnetwork"
  type        = string
  default     = "agent-subnetwork"
}

variable "ip_cidr_range" {
  description = "The IP range in CIDR notation for the subnetwork"
  type        = string
  default     = "10.0.0.0/16"
}

variable "network_attachment_name" {
  description = "Name of the Private Service Connect network attachment"
  type        = string
  default     = "agent-network-attachment"
}
