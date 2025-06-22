# nbiot_detector_core

## 📕 Table Of Contents

<!--ts-->

- 🌟 [System Architecture](#️-system-architecture)
- 📁 [Repository Structure](#-repository-structure)
- 🚀 [Getting Started](#-getting-started)

## 🌟 System Architecture
<p align="center">
<img src="./images/system-architecture.png" width=100% height=100%>

<p align="center">
    System Architecture
</p>

## 📁 Repository Structure
```shell
./nbiot_detector_core/
├── Dockerfile
├── Jenkinsfile
├── README.md
├── app
│   ├── main.py
│   ├── model_definition.py
│   ├── requirements.txt
│   └── saved_assets
│       ├── best_nbiot_detector.pth
│       └── nbiot_multi_device_scaler.gz
├── docker-compose.yaml
├── example.csv
├── kubernetes
│   ├── Dockerfile.jenkins
│   ├── Dockerfile.jenkins-agent
│   ├── base
│   │   ├── ingress.yaml
│   │   ├── jenkins-01-volume.yaml
│   │   └── jenkins-helm-role-and-role-binding.yaml
│   └── helm
│       ├── app-nbiot-detector
│       ├── elasticsearch
│       ├── filebeat
│       ├── ingress-nginx
│       ├── jaeger-all-in-one
│       ├── jenkins
│       ├── kibana
│       └── kube-prometheus-stack
├── local
├── pytest.ini
├── notebooks
│   ├── main.ipynb
├── scripts
│   ├── bootstrap.sh
│   └── cleanup.sh
├── terraform
│   ├── main.tf
│   ├── prod.tfvars
│   ├── outputs.tf
│   └── variables.tf
└── tests
    ├── __init__.pyc
    └── test_main.py
```

## 🚀 Getting Started

### Run on local
Prerequisites

- Docker version 25 or above
- Helm version 3 or above
- Minikube version 1.35.0 or above

```bash
cd scripts
chmod +x bootstrap.sh && bash bootstrap.sh local
```

### Run on production
Prerequisites

- Docker version 25 or above
- Helm version 3 or above
- Terraform version 1.12.0 or above
- Google Cloud SDK 522.0.0
- core 2025.05.09
- gcloud-crc32c 1.0.0
- gke-gcloud-auth-plugin 0.5.10
- gsutil 5.34

Login to GCP with CLI
```shell
gcloud auth application-default login
```

And deploy it to cloud
```shell
cd scripts
chmod +x bootstrap.sh && bash bootstrap.sh prod
```