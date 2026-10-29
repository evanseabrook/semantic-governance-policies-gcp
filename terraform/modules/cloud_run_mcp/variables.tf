variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
}

variable "region" {
  type        = string
  description = "The Google Cloud Region"
}

variable "service_name" {
  type        = string
  description = "Name of the Cloud Run MCP service"
  default     = "customer-policy-mcp-service"
}

variable "container_image" {
  type        = string
  description = "Full Docker image URI for the MCP server"
}

variable "service_account_email" {
  type        = string
  description = "Service Account email under which the Cloud Run service executes"
}

variable "invoker_sa_email" {
  type        = string
  description = "Service Account email allowed to invoke the service (Agent Engine / Gateway)"
}
