# Ref: https://github.com/terraform-google-modules/terraform-google-kubernetes-engine/blob/master/examples/simple_autopilot_public
# To define that we will use GCP
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.35.0" // Provider version
    }
  }
  required_version = ">=1.12.0" // Terraform version
}

// The library with methods for creating and
// managing the infrastructure in GCP, this will
// apply to all the resources in the project
provider "google" {
  project = var.project_id
  region  = var.region
}


// Google Kubernetes Engine
resource "google_container_cluster" "primary" {
  name     = "${var.project_id}-gke"
  location = var.region

  initial_node_count = 2

  deletion_protection      = var.deletion_protection
  remove_default_node_pool = true
}

resource "google_container_node_pool" "primary_preemptible_nodes" {
  name       = "${var.project_id}-gke-node-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = var.node_count

  node_config {
    preemptible  = false
    machine_type = var.machine_type // e2-medium - 1 vCPU , 4Gi Memory
    spot         = true
    disk_size_gb = 30
  }


}