variable "project_id" {
  description = "The project ID to host the cluster in"
  default     = "nbiot-detector"
}

variable "region" {
  description = "The region the cluster in"
  default     = "asia-southeast1-b"
}

variable "deletion_protection" {
  description = "For testing purpose"
  default     = true
}
variable "node_count" {
  description = "Total nodes in GKE cluster"
  default     = 4
}

variable "machine_type" {
  description = "Node pool machine types"
  default     = "e2-medium"
}