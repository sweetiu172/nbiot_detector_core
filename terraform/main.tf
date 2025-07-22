# Ref: https://github.com/terraform-google-modules/terraform-google-kubernetes-engine/blob/master/examples/simple_autopilot_public
# To define that we will use GCP
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.41.0" // Provider version
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


# // Google Kubernetes Engine
# resource "google_container_cluster" "primary" {
#   name     = "${var.project_id}-gke"
#   location = var.region

#   initial_node_count = 2

#   deletion_protection      = var.deletion_protection
#   remove_default_node_pool = true
# }

# resource "google_container_node_pool" "primary_preemptible_nodes" {
#   name       = "${var.project_id}-gke-node-pool"
#   location   = var.region
#   cluster    = google_container_cluster.primary.name
#   node_count = var.node_count

#   node_config {
#     preemptible  = false
#     machine_type = var.machine_type // e2-medium - 1 vCPU , 4Gi Memory
#     spot         = true
#     disk_size_gb = 30
#   }


# }


// Networking
resource "google_compute_network" "vpc" {
  name                    = "${var.project_id}-vpc"
  auto_create_subnetworks = false // We will create subnets manually
}

resource "google_compute_subnetwork" "private_subnet" {
  name                     = "${var.project_id}-private-subnet"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  private_ip_google_access = true
}

resource "google_compute_subnetwork" "public_subnet" {
  name          = "${var.project_id}-public-subnet"
  ip_cidr_range = "10.0.2.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

// Cloud Router and NAT for private node internet access
resource "google_compute_router" "router" {
  name    = "${var.project_id}-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.project_id}-nat-gateway"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

// Google Kubernetes Engine
resource "google_container_cluster" "primary" {
  name                     = "${var.project_id}-gke"
  location                 = "${var.region}-b"
  remove_default_node_pool = true
  initial_node_count       = 1
  network                  = google_compute_network.vpc.id
  subnetwork               = google_compute_subnetwork.private_subnet.id
  deletion_protection      = var.deletion_protection

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false // Control plane accessible from the public internet
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }
}

resource "google_container_node_pool" "primary_preemptible_nodes" {
  name       = "${var.project_id}-gke-node-pool"
  location   = "${var.region}-b"
  cluster    = google_container_cluster.primary.name
  node_count = var.node_count

  node_config {
    preemptible  = false
    machine_type = var.machine_type
    spot         = true
    disk_size_gb = 30

    // Associate nodes with the private subnet
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
  }
}