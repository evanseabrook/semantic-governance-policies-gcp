variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
}

variable "region" {
  type        = string
  description = "The Google Cloud Region"
  default     = "us-central1"
}

variable "image_tag" {
  type        = string
  description = "Docker image tag for the MCP server container"
  default     = "latest"
}

variable "enable_apis" {
  type        = string
  description = "Whether to manage and enable GCP service APIs via Terraform"
  default     = true
}
