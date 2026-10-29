variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
}

variable "region" {
  type        = string
  description = "The Google Cloud Region"
}

variable "repository_id" {
  type        = string
  description = "Artifact Registry Docker repository ID"
  default     = "customer-mcp-repo"
}
