#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Paths are relative to the scripts directory if run from there
HELM_CHARTS_DIR="../kubernetes/helm"
TERRAFORM_DIR="../terraform"
TF_VARS_FILE="prod.tfvars" # This file is expected inside TERRAFORM_DIR
K8S_BASE_MANIFESTS_DIR="../kubernetes/base"

# Define your specific namespaces
K8S_NAMESPACES_LIST=("ingress-nginx" "jenkins" "monitoring" "logging" "tracing" "nbiot-detector" "argocd" "cloudflared")

# --- Helper Functions ---
log_info() {
  echo "INFO: $1" >&2 # MODIFIED: Redirect to stderr
}

log_error() {
  echo "ERROR: $1" >&2
}

log_warning() {
  echo "WARNING: $1" >&2
}

check_command_exists() {
  command -v "$1" >/dev/null 2>&1 || { log_error "$1 is required but not installed. Aborting."; exit 1; }
}

# Function to deploy a specific Helm chart to a specific namespace
deploy_chart() {
  local chart_dir_name="$1"
  local target_namespace="$2"
  local chart_path="$HELM_CHARTS_DIR/$chart_dir_name"
  local release_name="$chart_dir_name"

  if [ ! -d "$chart_path" ] || [ ! -f "$chart_path/Chart.yaml" ]; then
    log_error "Chart directory '$chart_path' not found or does not contain a Chart.yaml. Deployment of '$release_name' will be skipped."
    return 1 # set -e will cause script to exit if not handled by caller
  fi

  log_info "Deploying Helm chart '$release_name' from '$chart_path' to namespace '$target_namespace'..."
  local values_file="$chart_path/values.yaml"
  if [ "$target_namespace" == "argocd" ]; then
    values_file="$chart_path/values.extended.yaml"
  fi
  local helm_args=()

  helm_args+=("upgrade" "--install" "$release_name" "$chart_path" "--namespace" "$target_namespace" "--create-namespace")

  if [ -f "$values_file" ]; then
    helm_args+=("-f" "$values_file")
    log_info "Using values file: $values_file"
  else
    log_info "No specific values.yaml found for '$release_name' at '$values_file', using default chart values."
  fi

  if [ -d "$chart_path/charts" ] && [ -n "$(ls -A "$chart_path/charts")" ]; then
      log_info "Chart '$release_name' has subcharts. Running helm dependency update..."
      # helm dependency update "$chart_path"
  fi

  helm "${helm_args[@]}"
  log_info "Successfully deployed Helm chart '$release_name' to namespace '$target_namespace'."
  return 0
}

# Function to get the external IP of the ingress-nginx controller
get_ingress_external_ip() {
  local service_name="ingress-nginx-controller"
  local service_namespace="ingress-nginx"
  local retry_count=0
  local max_retries=30
  local retry_interval=10
  local current_external_ip=""

  log_info "Attempting to get External IP for service '$service_name' in namespace '$service_namespace'..."
  while [ $retry_count -lt $max_retries ]; do
    current_external_ip=$(kubectl get service "$service_name" -n "$service_namespace" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
    if [[ -n "$current_external_ip" && "$current_external_ip" != "<none>" && "$current_external_ip" != "<pending>" ]]; then
      log_info "Found External IP: $current_external_ip"
      echo "$current_external_ip"
      return 0
    fi
    retry_count=$((retry_count + 1))
    if [ $retry_count -lt $max_retries ]; then # Avoid logging "Retrying" on the last attempt if it's about to fail
        log_info "External IP not available yet for '$service_name'. Retrying (${retry_count}/${max_retries})..."
    fi
    sleep "$retry_interval"
  done

  log_error "Failed to get External IP for '$service_name' in namespace '$service_namespace' after $max_retries retries."
  echo ""
  return 1
}

# Function to print DNS names from processed Ingress file
print_ingress_dns_names() {
  local processed_file="$1"
  if [ ! -f "$processed_file" ]; then
    log_warning "Processed ingress file '$processed_file' not found. Cannot print DNS names."
    return
  fi

  log_info "--- Deployed Ingress DNS Names (from $processed_file) ---"
  local dns_names_found=0
  grep -E '^\s*- host:' "$processed_file" | awk '{print $3}' | while IFS= read -r line; do
    if [[ -n "$line" ]]; then
      log_info "  Host: http://$line" # log_info prints to stderr, which is fine for console output
      dns_names_found=1
    fi
  done

  if [ "$dns_names_found" -eq 0 ]; then
    log_info "  No DNS names found matching pattern in $processed_file."
  fi
}

# Function to apply manifests from ../kubernetes/base
apply_base_kubernetes_manifests() {
  log_info "--- Applying Kubernetes Base Manifests from $K8S_BASE_MANIFESTS_DIR ---"

  local jenkins_volume_file="$K8S_BASE_MANIFESTS_DIR/jenkins-01-volume.yaml"
  local jenkins_role_binding_file="$K8S_BASE_MANIFESTS_DIR/jenkins-sa-rbac.yaml"
  local jenkins_ssh_sa="$K8S_BASE_MANIFESTS_DIR/jenkins-rbac-ssh.yaml"

  if [ -f "$jenkins_volume_file" ]; then
    log_info "Applying $jenkins_volume_file to 'jenkins' namespace..."
    kubectl apply -f "$jenkins_volume_file"
  else
    log_warning "$jenkins_volume_file not found. Skipping."
  fi

  if [ -f "$jenkins_role_binding_file" ]; then
    log_info "Applying $jenkins_role_binding_file to 'jenkins' namespace..."
    kubectl apply -f "$jenkins_role_binding_file"
  else
    log_warning "$jenkins_role_binding_file not found. Skipping."
  fi

  if [ -f "$jenkins_ssh_sa" ]; then
    log_info "Applying $jenkins_ssh_sa"
    kubectl apply -f "$jenkins_ssh_sa"
  else
    log_warning "$jenkins_ssh_sa not found. Skipping."
  fi

  log_info "Base Kubernetes manifests application process complete."
}

apply_argocd_kubernetes_manifests() {
  log_info "--- Applying Kubernetes Base Manifests from $K8S_BASE_MANIFESTS_DIR ---"

  # Define directories and specific files
  local argocd_manifests_dir="$K8S_BASE_MANIFESTS_DIR/argocd"

  # --- Apply all manifests from the argocd directory ---
  if [ -d "$argocd_manifests_dir" ]; then
    log_info "Applying all manifests from $argocd_manifests_dir..."
    # Loop through all .yaml files in the directory
    for manifest_file in "$argocd_manifests_dir"/*.yaml; do
      if [ -f "$manifest_file" ]; then
        local filename
        filename=$(basename "$manifest_file")

        log_info "Applying $filename..."
        kubectl apply -f "$manifest_file"

        # If the manifest we JUST applied was for Elasticsearch, wait for it to initialize
        if [ "$filename" == "elasticsearch.yaml" ]; then
          log_info "Waiting 6 minutes for Elasticsearch to initialize after applying..."
          sleep 360
        fi
      fi
    done
  else
    log_warning "Manifests directory not found: $argocd_manifests_dir. Skipping."
  fi

  log_info "ArgoCD Kubernetes manifests application process complete."
}


# Function to print default service passwords
print_service_passwords() {
  log_info "--- Default Service Credentials (Passwords are typically stored in Kubernetes Secrets) ---"
  # local external_ip_for_url="${1:-}" # Pass INGRESS_EXTERNAL_IP if available for URLs
  log_info "Run at local: kubectl --namespace nbiot-detector port-forward svc/app-nbiot-detector 8000:8000"
  log_info "Run at local: kubectl --namespace tracing port-forward svc/jaeger-all-in-one 16686:16686"
  echo >&2
  # Jenkins
  local jenkins_release_name="jenkins"
  local jenkins_namespace="jenkins"
  # Common secret name pattern for Jenkins chart
  local jenkins_secret_name="jenkins"
  log_info "Attempting to retrieve Jenkins admin password..."
  local jenkins_password
  local jenkins_username
  # Suppress errors from kubectl if secret or key not found
  jenkins_password=$(kubectl get secret "$jenkins_secret_name" -n "$jenkins_namespace" -o jsonpath='{.data.jenkins-admin-password}' 2>/dev/null | base64 --decode 2>/dev/null || echo "")
  jenkins_username=$(kubectl get secret "$jenkins_secret_name" -n "$jenkins_namespace" -o jsonpath='{.data.jenkins-admin-user}' 2>/dev/null | base64 --decode 2>/dev/null || echo "")
  if [[ -n "$jenkins_password" ]]; then
    log_info "Jenkins Admin User: $jenkins_username"
    log_info "Jenkins Admin Password: $jenkins_password"
    log_info "Run at local: kubectl --namespace jenkins port-forward svc/jenkins 8080:8080"
  else
    log_warning "Could not retrieve Jenkins admin password from secret '$jenkins_secret_name'."
    log_info "  Check Jenkins chart (values.yaml or notes) for how admin password is set or retrieved."
  fi
  echo >&2 # Blank line to stderr for readability in logs

  # Grafana (from kube-prometheus-stack)
  local grafana_release_name="kube-prometheus-stack"
  local grafana_namespace="monitoring"
  local grafana_secret_name="${grafana_release_name}-grafana"
  log_info "Attempting to retrieve Grafana admin password..."
  local grafana_password
  grafana_password=$(kubectl get secret "$grafana_secret_name" -n "$grafana_namespace" -o jsonpath='{.data.admin-password}' 2>/dev/null | base64 --decode 2>/dev/null || echo "")
  if [[ -n "$grafana_password" ]]; then
    log_info "Grafana Admin User: admin"
    log_info "Grafana Admin Password: $grafana_password"
    log_info "Run at local: kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80"
    # If you have an Ingress for Grafana similar to Jenkins, you can add its URL too.
  else
    log_warning "Could not retrieve Grafana admin password from secret '$grafana_secret_name'."
  fi
  echo >&2

  # Elasticsearch
  local es_release_name="elasticsearch"
  local es_namespace="logging"
  # Common secret name for Elastic official chart's 'elastic' user
  local es_secret_name_official="${es_release_name}-es-elastic-user"
  # Common secret name for Bitnami chart's 'elastic' user password
  local es_secret_name_bitnami="elasticsearch-master-credentials"
  log_info "Attempting to retrieve Elasticsearch 'elastic' user password..."
  local es_password=""

  # Try official chart secret pattern
  es_password=$(kubectl get secret "$es_secret_name_official" -n "$es_namespace" -o jsonpath='{.data.elastic}' 2>/dev/null | base64 --decode 2>/dev/null || echo "")
  # kubectl get secret elasticsearch-master-credentials -n logging -o jsonpath='{.data.elastic}' 2>/dev/null | base64 --decode

  # If not found, try Bitnami chart secret pattern
  if [[ -z "$es_password" ]]; then
    es_password=$(kubectl get secret "$es_secret_name_bitnami" -n "$es_namespace" -o jsonpath='{.data.password}' 2>/dev/null | base64 --decode 2>/dev/null || echo "")
  fi

  if [[ -n "$es_password" ]]; then
    log_info "Elasticsearch User: elastic"
    log_info "Elasticsearch Password: $es_password"
    log_info "Run at local: kubectl port-forward svc/kibana-kibana -n logging 5601:5601"
  else
    log_warning "Could not retrieve Elasticsearch 'elastic' user password."
    log_info "  Tried secrets like '$es_secret_name_official' (key: elastic) and '$es_secret_name_bitnami' (key: password)."
    log_info "  Elasticsearch chart defaults or secret names may vary."
  fi

  # ArgoCD
  local argocd_release_name="argo-cd"
  local argocd_namespace="argocd"
  local argocd_secret_name_official="${argocd_release_name}-initial-admin-secret"
  log_info "Attempting to retrieve ArgoCD 'admin' user password..."

  local argocd_password=""
  # kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
  argocd_password=$(kubectl -n $argocd_namespace get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 --decode 2>/dev/null || echo "")
  
  if [[ -n "$argocd_password" ]]; then
    log_info "ArgoCD User: admin"
    log_info "ArgoCD Password: $argocd_password"
    log_info "Run at local: kubectl port-forward service/argo-cd-server -n argocd 8080:80"
  else
    log_warning "Could not retrieve ArgoCD 'admin' user password."
  fi
  log_info "----------------------------------" # End of credentials section
}


# --- Main Logic ---

if [ -z "$1" ]; then
  log_error "Usage: $0 <local|prod>"
  exit 1
fi

ENVIRONMENT=$1

check_command_exists "kubectl"
check_command_exists "helm"

if [ "$ENVIRONMENT" == "local" ]; then
  log_info "Starting LOCAL deployment..."
  check_command_exists "minikube"
  log_info "Starting Minikube..."
  minikube start


elif [ "$ENVIRONMENT" == "prod" ]; then
  log_info "Starting PRODUCTION deployment..."
  check_command_exists "terraform"
  check_command_exists "gcloud"

  log_info "Navigating to Terraform directory: $TERRAFORM_DIR"
  cd "$TERRAFORM_DIR"

  log_info "Initializing Terraform..."
  terraform init -upgrade

  log_info "Applying Terraform configuration (this may take a while)..."
  terraform apply -var-file="$TF_VARS_FILE" -auto-approve

  log_info "Terraform apply completed. Configuring kubectl for GKE..."
  CLUSTER_NAME=$(terraform output -raw cluster_name 2>/dev/null || echo "")
  CLUSTER_LOCATION=$(terraform output -raw cluster_location 2>/dev/null || echo "")
  GCLOUD_PROJECT=$(terraform output -raw project_id 2>/dev/null || echo "")

  if [ -z "$CLUSTER_NAME" ] || [ -z "$CLUSTER_LOCATION" ] || [ -z "$GCLOUD_PROJECT" ]; then
    log_error "Could not retrieve all cluster details (name, location, project_id) from Terraform outputs."
    # ... (rest of error message) ...
    exit 1
  fi

  log_info "Attempting to configure kubectl for GKE cluster: '$CLUSTER_NAME' in '$CLUSTER_LOCATION' (project: '$GCLOUD_PROJECT')"
  gcloud container clusters get-credentials "$CLUSTER_NAME" --location "$CLUSTER_LOCATION" --project "$GCLOUD_PROJECT"

  log_info "Navigating back to scripts directory..." # Assuming this script is in a 'scripts' subdirectory
  cd ../scripts

else
  log_error "Invalid environment specified. Choose 'local' or 'prod'."
  exit 1
fi

# --- Common Steps for both environments after cluster is ready ---
log_info "Creating Kubernetes namespaces (if they don't exist)..."
for K8S_NAMESPACE in "${K8S_NAMESPACES_LIST[@]}"; do
  if ! kubectl get namespace "$K8S_NAMESPACE" > /dev/null 2>&1; then
    log_info "Creating namespace: $K8S_NAMESPACE"
    kubectl create namespace "$K8S_NAMESPACE" || log_warning "Namespace '$K8S_NAMESPACE' might already exist or creation failed."
  else
    log_info "Namespace '$K8S_NAMESPACE' already exists."
  fi
done
log_info "Namespace creation step complete."
echo >&2 # Blank line to stderr for readability

log_info "Starting Helm chart deployments based on defined mapping..."
# deploy_chart "ingress-nginx" "ingress-nginx"
deploy_chart "kube-prometheus-stack" "monitoring"
deploy_chart "argo-cd" "argocd"
# deploy_chart "cloudflare-tunnel-remote" "cloudflared"
log_info "Helm chart deployment process complete."
echo >&2 # Blank line to stderr for readability


# Apply base Kubernetes manifests
# apply_base_kubernetes_manifests will use the INGRESS_EXTERNAL_IP (which might be empty)
apply_base_kubernetes_manifests
echo >&2 # Blank line to stderr for readability

# Apply ArgoCD helm chart
apply_argocd_kubernetes_manifests
echo >&2 # Blank line to stderr for readability

# INGRESS_EXTERNAL_IP=""

# set +e
# if [ "$ENVIRONMENT" == "prod" ]; then
#   INGRESS_EXTERNAL_IP=$(get_ingress_external_ip)
#   GET_IP_STATUS=$?
#   if [ $GET_IP_STATUS -ne 0 ] || [ -z "$INGRESS_EXTERNAL_IP" ]; then
#     log_error "Could not obtain Ingress External IP. Some functionalities in base manifests (like ingress rules) might not work correctly."
#     # INGRESS_EXTERNAL_IP will be empty, apply_base_kubernetes_manifests will skip ingress part
#   fi
#   echo >&2 # Blank line to stderr for readability
# fi
# set -e

# Print service passwords at the end
# print_service_passwords "$INGRESS_EXTERNAL_IP"
print_service_passwords

log_info "$ENVIRONMENT deployment process completed! 🚀"