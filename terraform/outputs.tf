output "project_id" {
  description = "The GCP project ID where the GKE cluster is deployed."
  value       = google_container_cluster.primary.project
}

output "cluster_name" {
  description = "The name of the GKE cluster."
  value       = google_container_cluster.primary.name
}

output "cluster_location" {
  description = "The location (zone or region) of the GKE cluster."
  value       = google_container_cluster.primary.location
}