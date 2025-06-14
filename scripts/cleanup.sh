#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
# set -e # Commented out to allow script to continue if a single delete fails, to attempt all cleanup operations.

# --- Configuration ---
# Paths are relative to the ./scripts/ directory where this script is located
TERRAFORM_DIR="../terraform"
TF_VARS_FILE="mlops.tfvars" # Expected inside TERRAFORM_DIR
K8S_BASE_MANIFESTS_DIR="../kubernetes/base"

# Namespaces to delete (excluding 'default' as it's a system namespace)
K8S_NAMESPACES_TO_DELETE=("ingress-nginx" "jenkins" "monitoring" "logging" "tracing")

# Mapping of namespaces to Helm releases.
# Release names should match those used in deploy.sh (typically chart directory names)
declare -A HELM_RELEASES_MAP
HELM_RELEASES_MAP["ingress-nginx"]="ingress-nginx"
HELM_RELEASES_MAP["jenkins"]="jenkins"
HELM_RELEASES_MAP["monitoring"]="kube-prometheus-stack"
HELM_RELEASES_MAP["logging"]="kibana elasticsearch filebeat"
HELM_RELEASES_MAP["tracing"]="jaeger-all-in-one"
HELM_RELEASES_MAP["default"]="app-nbiot-detector"

# --- Helper Functions ---
log_info() {
  echo "INFO: $1" >&2 # Log to stderr
}

log_error() {
  echo "ERROR: $1" >&2
}

log_warning() {
  echo "WARNING: $1" >&2
}

check_command_exists() {
  command -v "$1" >/dev/null 2>&1 || { log_error "$1 is required but not installed. Aborting this script."; exit 1; }
}

# Function to uninstall Helm releases
uninstall_helm_releases() {
  log_info "--- Uninstalling Helm Releases ---"
  if ! command -v helm >/dev/null 2>&1; then
    log_error "Helm is not installed. Cannot uninstall Helm releases."
    return 1
  fi

  for ns in "${!HELM_RELEASES_MAP[@]}"; do
    releases_in_ns="${HELM_RELEASES_MAP[$ns]}"
    log_info "Checking namespace: $ns for releases: $releases_in_ns"
    for release_name in $releases_in_ns; do
      log_info "Attempting to uninstall Helm release '$release_name' from namespace '$ns'..."
      if helm status "$release_name" --namespace "$ns" > /dev/null 2>&1; then
        if helm uninstall "$release_name" --namespace "$ns"; then
          log_info "Successfully uninstalled Helm release '$release_name' from namespace '$ns'."
        else
          log_warning "Failed to uninstall Helm release '$release_name' from namespace '$ns'."
        fi
      else
        log_info "Helm release '$release_name' not found in namespace '$ns'. Skipping."
      fi
    done
  done
  log_info "Helm release uninstallation process complete."
}

# Function to delete base Kubernetes manifests
delete_base_kubernetes_manifests() {
  log_info "--- Deleting Kubernetes Base Manifests from $K8S_BASE_MANIFESTS_DIR ---"
  if ! command -v kubectl >/dev/null 2>&1; then
    log_error "kubectl is not installed. Cannot delete base manifests."
    return 1
  fi

  # Adjusted to use ingress.yaml as per your new structure
  local ingress_file="$K8S_BASE_MANIFESTS_DIR/ingress.yaml"
  local jenkins_volume_file="$K8S_BASE_MANIFESTS_DIR/jenkins-01-volume.yaml"
  local jenkins_role_binding_file="$K8S_BASE_MANIFESTS_DIR/jenkins-helm-role-and-role-binding.yaml"

  if [ -f "$ingress_file" ]; then
    log_info "Deleting resources defined in $ingress_file..."
    kubectl delete -f "$ingress_file" --ignore-not-found=true || log_warning "Deletion command for $ingress_file encountered issues."
  else
    log_warning "$ingress_file not found. Skipping its deletion."
  fi

  if [ -f "$jenkins_volume_file" ]; then
    log_info "Deleting $jenkins_volume_file from 'jenkins' namespace..."
    kubectl delete -f "$jenkins_volume_file" --ignore-not-found=true || log_warning "Failed to delete $jenkins_volume_file from 'jenkins' namespace."
  else
    log_warning "$jenkins_volume_file not found. Skipping its deletion."
  fi

  if [ -f "$jenkins_role_binding_file" ]; then
    log_info "Attempting to delete resources from $jenkins_role_binding_file..."
    # Deployed with -n jenkins. Attempt deletion from that namespace.
    # If it also contained cluster-scoped items, a second broader delete might be needed if the first misses them,
    # but `kubectl delete -f` should handle resources listed in the file.
    kubectl delete -f "$jenkins_role_binding_file" --ignore-not-found=true
    # To be thorough for any cluster-scoped resources potentially missed if -n jenkins filtered them out:
    kubectl delete -f "$jenkins_role_binding_file" --ignore-not-found=true
    log_info "Deletion attempt for resources in $jenkins_role_binding_file complete."
  else
    log_warning "$jenkins_role_binding_file not found. Skipping its deletion."
  fi

  log_info "Base Kubernetes manifests deletion process complete."
}

# Function to delete specified Kubernetes namespaces
delete_k8s_namespaces() {
  log_info "--- Deleting Kubernetes Namespaces ---"
  if ! command -v kubectl >/dev/null 2>&1; then
    log_error "kubectl is not installed. Cannot delete namespaces."
    return 1
  fi

  for ns in "${K8S_NAMESPACES_TO_DELETE[@]}"; do
    log_info "Attempting to delete namespace '$ns'..."
    if kubectl get namespace "$ns" > /dev/null 2>&1; then
      if kubectl delete namespace "$ns" --wait=true --timeout=3m; then # Increased timeout slightly
         log_info "Deletion initiated for namespace '$ns'. It may take some time to fully terminate."
      else
         log_warning "Failed to delete namespace '$ns' or timed out. Please check manually: 'kubectl get namespace $ns'"
      fi
    else
      log_info "Namespace '$ns' not found. Skipping."
    fi
  done
  log_info "Namespace deletion process complete. Monitor termination with 'kubectl get namespaces'."
}

# --- Main Logic ---

echo "*****************************************************************" >&2
echo "* WARNING: This script will delete resources. Review carefully! *" >&2
echo "*****************************************************************" >&2
read -r -p "Are you sure you want to continue with cleanup? (yes/no): " confirmation
if [[ "$confirmation" != "yes" ]]; then
  log_info "Cleanup aborted by user."
  exit 0
fi

if [ -z "$1" ]; then
  log_error "Usage: $0 <local|prod>"
  exit 1
fi

ENVIRONMENT=$1

# Verify base dependencies for Kubernetes operations
check_command_exists "kubectl"
check_command_exists "helm"

if [ "$ENVIRONMENT" == "local" ]; then
  # --- Local Cleanup (Minikube) ---
  log_info "Starting LOCAL cleanup..."
  check_command_exists "minikube" 

  log_info "Assuming kubectl is configured for your Minikube cluster."
  log_info "Run 'minikube status' in another terminal to verify if needed."

  uninstall_helm_releases
  delete_base_kubernetes_manifests 
  delete_k8s_namespaces

  log_info "--- Minikube Cluster Management (Optional) ---"
  log_info "If you wish to stop the Minikube VM, run: minikube stop"
  log_info "If you wish to delete the entire Minikube cluster, run: minikube delete"
  log_info "LOCAL cleanup of deployed applications and namespaces complete."

elif [ "$ENVIRONMENT" == "prod" ]; then
  # --- Production Cleanup (GKE via Terraform) ---
  log_info "Starting PRODUCTION cleanup..."
  check_command_exists "terraform" # Using .exe for consistency with your deploy script
  check_command_exists "gcloud" 

  log_warning "PRODUCTION: Ensure kubectl is configured to point to the correct GKE cluster you intend to clean up!"
  log_info "You can verify with 'kubectl config current-context' and 'kubectl get nodes'."
  read -r -p "Is kubectl configured for the correct GKE production cluster? (yes/no): " prod_confirmation
  if [[ "$prod_confirmation" != "yes" ]]; then
    log_info "Production cleanup aborted. Please configure kubectl correctly."
    exit 1
  fi

  # 1. Clean Kubernetes resources first
  uninstall_helm_releases
  delete_base_kubernetes_manifests 
  delete_k8s_namespaces

  # 2. Destroy Terraform-managed infrastructure
  log_info "--- Destroying GKE Infrastructure with Terraform ---"
  log_info "Navigating to Terraform directory: $TERRAFORM_DIR (from $(pwd))"
  if [ ! -d "$TERRAFORM_DIR" ]; then
      log_error "Terraform directory '$TERRAFORM_DIR' not found. Cannot run terraform destroy."
      exit 1
  fi
  cd "$TERRAFORM_DIR" || { log_error "Failed to navigate to Terraform directory: $TERRAFORM_DIR"; exit 1; }

  log_info "Current directory: $(pwd)"
  log_info "Initializing Terraform (required before destroy if .terraform directory is missing)..."
  # For destroy, init without -upgrade is usually fine, but -upgrade doesn't hurt.
  terraform init -upgrade || log_warning "Terraform init failed. If already initialized, destroy might still work."

  log_info "Running 'terraform destroy'. This will remove ALL infrastructure defined in your Terraform configuration."
  log_warning "Review the plan carefully when prompted by Terraform (unless -auto-approve is used)."
  
  # For safety, -auto-approve is not used by default. User will be prompted by Terraform.
  if terraform destroy -var-file="$TF_VARS_FILE"; then
    log_info "Terraform destroy completed successfully."
  else
    log_error "Terraform destroy failed. Please check the output and your GCP console."
  fi
  
  # Navigate back to the directory where the script was likely launched from (e.g., ../scripts relative to ../terraform)
  # If script is in ./scripts, and current dir is ./terraform, then `cd ../scripts`
  log_info "Navigating back to scripts directory..."
  cd ../scripts || log_warning "Could not navigate back to scripts directory. Current directory: $(pwd)"
  
  log_info "PRODUCTION cleanup process (including Terraform destroy) complete."

else
  log_error "Invalid environment specified. Choose 'local' or 'prod'."
  exit 1
fi

log_info "Cleanup script finished."