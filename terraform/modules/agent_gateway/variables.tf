variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region for the Agent Gateway"
  type        = string
}

variable "network_name" {
  description = "Name of the custom VPC network for DNS peering"
  type        = string
  default     = "agent-network"
}

variable "gateway_name" {
  description = "Name of the Agent Gateway"
  type        = string
  default     = "customer-policy-agent-gateway"
}

variable "connectivity_template_id" {
  description = "ID of the Agent Connectivity Template"
  type        = string
  default     = "customer-policy-agent-gateway-template"
}

variable "network_attachment_id" {
  description = "The Compute Network Attachment ID for egress connectivity"
  type        = string
}

variable "labels" {
  description = "Labels to apply to the Agent Gateway resources"
  type        = map(string)
  default = {
    managed-by = "terraform"
    tier       = "agent-governance"
  }
}
