output "staging_bucket_name" {
  description = "Name of the GCS staging bucket for Agent Engine"
  value       = google_storage_bucket.agent_staging.name
}

output "staging_bucket_url" {
  description = "URI of the GCS staging bucket"
  value       = "gs://${google_storage_bucket.agent_staging.name}"
}
