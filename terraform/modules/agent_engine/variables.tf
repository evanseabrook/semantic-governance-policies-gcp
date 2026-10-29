variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
}

variable "region" {
  type        = string
  description = "The Google Cloud Region"
}

variable "agent_engine_sa_email" {
  type        = string
  description = "Service Account email for Agent Engine"
}

variable "bucket_name" {
  type        = string
  description = "GCS Staging Bucket name for Agent Engine artifacts"
  default     = ""
}
