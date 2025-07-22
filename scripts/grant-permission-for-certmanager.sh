GCP_PROJECT_ID="nbiot-detector"
SA_NAME="cert-manager-dns01"

# Create the service account
gcloud iam service-accounts create ${SA_NAME} \
  --display-name="Service account for cert-manager DNS01 solver"

# Grant it the DNS Administrator role
gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} \
  --member="serviceAccount:${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/dns.admin"

# Create and download a key for the service account
gcloud iam service-accounts keys create key.json \
  --iam-account="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"