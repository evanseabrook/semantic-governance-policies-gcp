resource "google_cloud_run_v2_service" "mcp_service" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1024Mi"
        }
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 2
        period_seconds        = 5
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        period_seconds = 10
      }
    }
  }
}

# Grant run.invoker strictly to the authorized identity (Agent Engine SA / Gateway)
# No allUsers binding: unauthenticated requests are rejected with 401/403
resource "google_cloud_run_v2_service_iam_member" "mcp_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mcp_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.invoker_sa_email}"
}
