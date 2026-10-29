locals {
  staging_bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_id}-agent-engine-staging"
}

# GCS Bucket for staging Agent Engine artifacts
resource "google_storage_bucket" "agent_staging" {
  name                        = local.staging_bucket_name
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 30
    }
  }
}

# Grant Agent Engine SA permissions to read/write staging artifacts
resource "google_storage_bucket_iam_member" "agent_staging_access" {
  bucket = google_storage_bucket.agent_staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.agent_engine_sa_email}"
}
