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
}

# --- Add this resource ---
# Grant the SA permission to be used *by* Eventarc triggers for event delivery
resource "google_project_iam_member" "sa_eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.ingester.email}"

  depends_on = [google_service_account.ingester]
}
# -------------------------

# ----------  Buckets -----------------------------------------------------

resource "google_storage_bucket" "raw" {
  name                        = "${var.project_id}-docs-raw"
  location                    = var.region
  uniform_bucket_level_access = true
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

resource "google_compute_subnetwork" "subnet" {
  name          = "egress-net-${var.region}"
  ip_cidr_range = "10.255.0.0/24"
  network       = google_compute_network.vpc.id
  region        = var.region
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
# -------------------------------------------------------------

# ----------  Cloud SQL (PostgreSQL 16 + pgvector) ------------------------

resource "google_sql_database_instance" "pg" {
  name             = "docs-pg-db"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = "db-custom-1-3840"
    edition = "ENTERPRISE" 

    ip_configuration {
      ssl_mode                                      = "ENCRYPTED_ONLY"
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.vpc.id
      enable_private_path_for_google_cloud_services = true
    }
  }

  # Ensure the private connection is established first
  depends_on = [google_service_networking_connection.private_vpc_connection]
}

resource "google_sql_database" "db" {
  name     = "docs"
  instance = google_sql_database_instance.pg.name
}

# ----------  Cloud Run service ------------------------------------------

resource "google_cloud_run_v2_service" "document-ingester" {
  name     = "document-ingester"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    service_account                  = google_service_account.ingester.email
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.pg.connection_name]
      }
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.subnet.id
      }
    }

    containers {
      image = var.ingester_image_path

      env {
        name  = "RAW_BUCKET"
        value = google_storage_bucket.raw.name
      }
      env {
        name  = "PROCESSED_BUCKET"
        value = google_storage_bucket.processed.name
      }
      env {
        name  = "CLOUD_SQL_INSTANCE"
        value = google_sql_database_instance.pg.connection_name
      }
      env {
        name = "CLOUD_SQL_USER"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.db_user.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "CLOUD_SQL_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "CLOUD_SQL_DB"
        value = google_sql_database.db.name
      }
      env {
        name  = "LOCATION"
        value = var.model_region
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "CLOUDSQL_AUTH_PROXY_PRIVATE_IP"
        value = "true"
      }
      env {
        name  = "EMBED_MODEL"
        value = var.embed_model
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
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
}


# ----------  Eventarc trigger -------------------------------------------

# Grant the trigger's identity (ingester SA) permission to invoke Cloud Run
resource "google_cloud_run_v2_service_iam_member" "ingester_invoker" {
  project  = google_cloud_run_v2_service.document-ingester.project
  location = google_cloud_run_v2_service.document-ingester.location
  name     = google_cloud_run_v2_service.document-ingester.name

  role   = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.ingester.email}"

  depends_on = [google_cloud_run_v2_service.document-ingester]
}
# -----------------------------------------------------------------------

resource "google_eventarc_trigger" "gcs_finalize" {
  project  = var.project_id
  name     = "ingest-on-finalize"
  location = var.region
  # --- Event matching criteria ---
  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.raw.name
  }
  # --- Use the ingester service account to publish events ---
  # This SA needs roles/pubsub.publisher on the ingest_transport topic
  service_account = google_service_account.ingester.email # Trigger uses this SA

  # --- Destination is now the explicitly managed transport topic ---
  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.document-ingester.name
      region  = var.region
    }
  }

  # Ensure necessary permissions are granted before creating the trigger
  depends_on = [
    google_project_iam_member.sa_eventarc_receiver
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
}

resource "google_secret_manager_secret_iam_member" "sa_secret_accessor_password" {
  secret_id = data.google_secret_manager_secret.db_password.id
  project   = data.google_secret_manager_secret.db_password.project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingester.email}"
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

# --- Add this resource ---
# Grant Pub/Sub service account permission to read bucket metadata for DLQ
resource "google_storage_bucket_iam_member" "dlq_bucket_reader" {
  bucket = google_storage_bucket.dlq_bucket.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_storage_bucket.dlq_bucket]
}
# -------------------------

# Grant Eventarc service agent permission to publish to the DLQ topic
resource "google_pubsub_topic_iam_member" "eventarc_dlq_publisher" {
  project = google_pubsub_topic.dlq_topic.project
  topic   = google_pubsub_topic.dlq_topic.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"

  depends_on = [google_pubsub_topic.dlq_topic]
}

