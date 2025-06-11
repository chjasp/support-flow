terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ----------  Service account ---------------------------------------------

resource "google_service_account" "ingester" {
  account_id   = "ingester-sa"
  display_name = "Cloud Run ingest service account"
}

resource "google_project_iam_member" "sa_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.ingester.email}"
}

resource "google_project_iam_member" "sa_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.ingester.email}"
}

resource "google_project_iam_member" "sa_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.ingester.email}"
  count = 0
}

# --- Add this resource ---
# Grant the SA permission to be used *by* Eventarc triggers for event delivery
resource "google_project_iam_member" "sa_eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.ingester.email}"

  depends_on = [google_service_account.ingester]
  count = 0
}
# -------------------------

# ----------  Buckets -----------------------------------------------------

resource "google_storage_bucket" "raw" {
  name                        = "${var.project_id}-docs-raw"
  location                    = var.region
  uniform_bucket_level_access = true

  cors {
    origin          = ["http://localhost:3000", "https://your-nextjs-app-*.a.run.app"]
    method          = ["GET", "PUT"]
    response_header = ["Content-Type", "Content-Length", "x-goog-meta-originalfilename"]
    max_age_seconds = 3600
  }
}

resource "google_storage_bucket" "processed" {
  name                        = "${var.project_id}-docs-processed"
  location                    = var.region
  uniform_bucket_level_access = true
}

# ----------  VPC for Cloud Run Egress ---------------------

resource "google_compute_network" "vpc" {
  name                    = "nexus-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet_ew1" {
  name          = "egress-net-europe-west1"
  ip_cidr_range = "10.255.1.0/24"
  network       = google_compute_network.vpc.id
  region        = "europe-west1"
  private_ip_google_access = true
}

# --- FIX: Add Private Services Access connection resources ---
resource "google_compute_global_address" "private_ip_alloc" {
  name          = "private-services-access-allocation"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.vpc.id
  address       = "192.168.0.0"
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]

  # Ensure the network and allocation exist first, and the API is enabled
  depends_on = [
    google_project_service.services["servicenetworking.googleapis.com"]
  ]
}

# ---------- Secret Manager Secrets (Data Sources) -----------------------

data "google_secret_manager_secret" "db_user" {
  secret_id = "docs-db-user"
  project   = var.project_id
}

data "google_secret_manager_secret_version" "db_user_latest" {
  secret  = data.google_secret_manager_secret.db_user.id
  project = var.project_id
}

data "google_secret_manager_secret" "db_password" {
  secret_id = "docs-db-password"
  project   = var.project_id
}

data "google_secret_manager_secret_version" "db_password_latest" {
  secret  = data.google_secret_manager_secret.db_password.id
  project = var.project_id
}

resource "google_secret_manager_secret_iam_member" "sa_secret_accessor_user" {
  secret_id = data.google_secret_manager_secret.db_user.id
  project   = data.google_secret_manager_secret.db_user.project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingester.email}"
  count = 0
}

resource "google_secret_manager_secret_iam_member" "sa_secret_accessor_password" {
  secret_id = data.google_secret_manager_secret.db_password.id
  project   = data.google_secret_manager_secret.db_password.project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingester.email}"
  count = 0
}

# ----------  Enable APIs -------------------------------------------------

resource "google_project_service" "services" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "eventarc.googleapis.com",
    "storage.googleapis.com",
    "sqladmin.googleapis.com",
    "vpcaccess.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "pubsub.googleapis.com"
  ])
  service = each.key
  disable_on_destroy = false
}

# ---------- Data source for Project Number -------------------------------
# Needed for service agent IAM bindings
data "google_project" "project" {
  project_id = var.project_id
}

# ---------- Eventarc Transport & Dead Letter Queue (DLQ) -----------------

# Dead Letter Topic
resource "google_pubsub_topic" "dlq_topic" {
  project = var.project_id
  name    = "ingest-dlq-topic"
}

# Dead Letter Bucket
resource "google_storage_bucket" "dlq_bucket" {
  project                     = var.project_id
  name                        = "${var.project_id}-ingest-dlq-bucket"
  location                    = var.region
  uniform_bucket_level_access = true
}

# Subscription to pull from DLQ topic and write to DLQ bucket
resource "google_pubsub_subscription" "dlq_subscription" {
  project = var.project_id
  name    = "ingest-dlq-to-gcs-sub"
  topic   = google_pubsub_topic.dlq_topic.id

  ack_deadline_seconds = 300 # Max value

  cloud_storage_config {
    bucket = google_storage_bucket.dlq_bucket.name
    filename_prefix = "dlq-message-"
    filename_suffix = ".json"
    max_bytes = 10485760 # 10 MiB
    max_duration = "300s"
  }

  # Ensure the topic and bucket exist first
  depends_on = [
    google_pubsub_topic.dlq_topic,
    google_storage_bucket.dlq_bucket
  ]
}

# Grant Pub/Sub service account permission to write to the DLQ bucket
resource "google_storage_bucket_iam_member" "dlq_bucket_writer" {
  bucket = google_storage_bucket.dlq_bucket.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_storage_bucket.dlq_bucket]
}

# Grant Pub/Sub service account permission to read bucket metadata for DLQ
resource "google_storage_bucket_iam_member" "dlq_bucket_reader" {
  bucket = google_storage_bucket.dlq_bucket.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_storage_bucket.dlq_bucket]
}

# Grant Eventarc service agent permission to publish to the DLQ topic
resource "google_pubsub_topic_iam_member" "eventarc_dlq_publisher" {
  project = google_pubsub_topic.dlq_topic.project
  topic   = google_pubsub_topic.dlq_topic.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"

  depends_on = [google_pubsub_topic.dlq_topic]
}

# --- Add Pub/Sub Service Account permissions on DLQ Topic ---
# Grant Pub/Sub SA permission to publish dead-lettered messages TO the DLQ topic
resource "google_pubsub_topic_iam_member" "pubsub_dlq_publisher" {
  project = google_pubsub_topic.dlq_topic.project
  topic   = google_pubsub_topic.dlq_topic.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_pubsub_topic.dlq_topic]
}

# ---------- Unified Content Processing Pub/Sub Infrastructure -----------

# Topic for URL and text content processing requests
resource "google_pubsub_topic" "content_processing" {
  project = var.project_id
  name    = "content-processing-topic"
}

# Subscription for content processing (push to Cloud Run)
resource "google_pubsub_subscription" "content_processing" {
  project = var.project_id
  name    = "content-processing-subscription"
  topic   = google_pubsub_topic.content_processing.id

  ack_deadline_seconds = 600 # 10 minutes for processing
  message_retention_duration = "604800s" # 7 days

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.backend.uri}/process-content"
    
    # Authentication for push endpoint
    oidc_token {
      service_account_email = google_service_account.ingester.email
    }
  }

  # Configure retry policy
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  # Configure dead letter policy to use our existing DLQ
  dead_letter_policy {
    dead_letter_topic = google_pubsub_topic.dlq_topic.id
    max_delivery_attempts = 5
  }

  depends_on = [
    google_pubsub_topic.content_processing,
    google_cloud_run_v2_service.backend,
    google_pubsub_topic.dlq_topic
  ]
}

# Grant ingester service account permission to publish to content processing topic
resource "google_pubsub_topic_iam_member" "content_processing_publisher" {
  project = google_pubsub_topic.content_processing.project
  topic   = google_pubsub_topic.content_processing.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.ingester.email}"

  depends_on = [google_pubsub_topic.content_processing]
}

# Grant Pub/Sub service account permission to invoke the Cloud Run service
resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker" {
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name

  role   = "roles/run.invoker"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_cloud_run_v2_service.backend]
}

# -----------------------------------------------------------------------


# ───────────────────────────────────────────────
#  Cloud Run – Next.js Frontend
# ───────────────────────────────────────────────

resource "google_service_account" "frontend" {
  account_id   = "frontend-sa"
  display_name = "Cloud Run Frontend service account"
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "frontend"
  location = "europe-west1" # limited domain mapping availability
  ingress  = "INGRESS_TRAFFIC_ALL"   # Public HTTP access
  deletion_protection = false

  template {
    service_account = google_service_account.frontend.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.subnet_ew1.id
      }
      egress = "ALL_TRAFFIC"
    }

    containers {
      image = var.frontend_image_path

      env {
        name  = "API_BASE_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
      env {
        name = "GCS_BUCKET_NAME"
        value = google_storage_bucket.raw.name
      }
      env {
        name  = "NEXTAUTH_URL"
        value = "https://bloomlake.de"
      }
      env {
        name = "GOOGLE_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = "frontend-google-client-id"
            version = "latest"
          }
        }
      }
      env {
        name = "GOOGLE_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = "frontend-google-client-secret"
            version = "latest"
          }
        }
      }
      env {
        name = "NEXTAUTH_SECRET"
        value_source {
          secret_key_ref {
            secret  = "frontend-nextauth-secret"
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.services["run.googleapis.com"],
    google_storage_bucket.raw
  ]
}

# Allow unauthenticated users to reach the site
resource "google_cloud_run_v2_service_iam_member" "frontend_public_invoker" {
  project  = google_cloud_run_v2_service.frontend.project
  location = google_cloud_run_v2_service.frontend.location
  name     = google_cloud_run_v2_service.frontend.name

  role   = "roles/run.invoker"
  member = "allUsers"

  depends_on = [google_cloud_run_v2_service.frontend]
}

# --- Secret Accessor permissions ---
# (Keep existing data sources and iam_member resources for secrets)
data "google_secret_manager_secret" "frontend_google_client_id" {
  secret_id = "frontend-google-client-id"
  project   = var.project_id
}

data "google_secret_manager_secret" "frontend_google_client_secret" {
  secret_id = "frontend-google-client-secret"
  project   = var.project_id
}

data "google_secret_manager_secret" "frontend_nextauth_secret" {
  secret_id = "frontend-nextauth-secret"
  project   = var.project_id
}

resource "google_secret_manager_secret_iam_member" "frontend_secret_accessor_google_id" {
  secret_id = data.google_secret_manager_secret.frontend_google_client_id.id
  project   = data.google_secret_manager_secret.frontend_google_client_id.project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.frontend.email}"
}

resource "google_secret_manager_secret_iam_member" "frontend_secret_accessor_google_secret" {
  secret_id = data.google_secret_manager_secret.frontend_google_client_secret.id
  project   = data.google_secret_manager_secret.frontend_google_client_secret.project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.frontend.email}"
}

resource "google_secret_manager_secret_iam_member" "frontend_secret_accessor_nextauth_secret" {
  secret_id = data.google_secret_manager_secret.frontend_nextauth_secret.id
  project   = data.google_secret_manager_secret.frontend_nextauth_secret.project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.frontend.email}"
}
# --- End Secret Accessor permissions ---

# --- Keep the backend invoker permission ---
resource "google_cloud_run_v2_service_iam_member" "backend_invoker_frontend" {
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name

  role   = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.frontend.email}"
}

# Secret-accessor bindings (reuse earlier pattern)
resource "google_secret_manager_secret_iam_member" "backend_secret_accessor_google_id" {
  secret_id = "backend-google-client-id"
  project   = var.project_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingester.email}"
}

# ───────────────────────────────────────────────
#  Cloud Run – Backend
# ───────────────────────────────────────────────

resource "google_cloud_run_v2_service" "backend" {
  name     = "backend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY" # Allow public ingress
  deletion_protection = false

  template {
    service_account = google_service_account.ingester.email

    scaling {
      min_instance_count = 1
      max_instance_count = 4
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.subnet_ew1.id
      }
    }

    containers {
      image = var.backend_image_path

      # Core environment configuration
      env {
        name  = "RAW_BUCKET"
        value = google_storage_bucket.raw.name
      }
      env {
        name  = "PROCESSED_BUCKET"
        value = google_storage_bucket.processed.name
      }
      env {
        name  = "LOCATION"
        value = var.model_region
      }
      env {
        name  = "GCP_LOCATION"
        value = var.model_region
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "EMBED_MODEL"
        value = var.embed_model
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "CONTENT_PROCESSING_TOPIC"
        value = google_pubsub_topic.content_processing.name
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.services["run.googleapis.com"],
    google_storage_bucket.raw
  ]
}

# Add public invoker binding for backend
resource "google_cloud_run_v2_service_iam_member" "backend_public_invoker" {
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name

  role   = "roles/run.invoker"
  member = "allUsers"

  depends_on = [google_cloud_run_v2_service.backend]
}

resource "google_project_iam_member" "sa_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.ingester.email}"
}
