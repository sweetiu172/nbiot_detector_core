# nbiot_detector
```java
Jenkins.instance.pluginManager.plugins.each { plugin ->
  println "- ${plugin.getShortName()}:${plugin.getVersion()}"
}
```
```sh
$ tree  ./nbiot_detector/ -L 4
```
```md
./nbiot_detector/
├── Dockerfile
├── Jenkinsfile
├── README.md
├── app
│   ├── __init__.py
│   ├── main.py
│   ├── model_definition.py
│   ├── requirements.txt
│   └── saved_assets
│       ├── best_nbiot_detector.pth
│       └── nbiot_multi_device_scaler.gz
├── docker-compose.yaml
├── kubernetes
│   ├── Dockerfile.jenkins
│   ├── Dockerfile.jenkins-agent
│   ├── base
│   │   ├── ingress.yaml
│   │   ├── jenkins-01-volume.yaml
│   │   └── jenkins-helm-role-and-role-binding.yaml
│   └── helm
│       ├── app-nbiot-detector
│       │   ├── Chart.yaml
│       │   ├── charts
│       │   ├── templates
│       │   └── values.yaml
│       ├── elasticsearch
│       │   ├── Chart.yaml
│       │   ├── Makefile
│       │   ├── README.md
│       │   ├── examples
│       │   ├── templates
│       │   └── values.yaml
│       ├── filebeat
│       │   ├── Chart.yaml
│       │   ├── Makefile
│       │   ├── README.md
│       │   ├── examples
│       │   ├── templates
│       │   └── values.yaml
│       ├── ingress-nginx
│       │   ├── Chart.yaml
│       │   ├── OWNERS
│       │   ├── README.md
│       │   ├── README.md.gotmpl
│       │   ├── changelog
│       │   ├── ci
│       │   ├── templates
│       │   ├── tests
│       │   └── values.yaml
│       ├── jenkins
│       │   ├── CHANGELOG.md
│       │   ├── Chart.yaml
│       │   ├── README.md
│       │   ├── UPGRADING.md
│       │   ├── VALUES.md
│       │   ├── VALUES.md.gotmpl
│       │   ├── jenkins-values.yaml
│       │   ├── templates
│       │   └── values.yaml
│       └── kube-prometheus-stack
│           ├── Chart.lock
│           ├── Chart.yaml
│           ├── README.md
│           ├── charts
│           ├── templates
│           └── values.yaml
├── local
│   ├── alertmanager
│   │   └── data
│   ├── elk
│   │   ├── elasticsearch
│   │   │   ├── Dockerfile
│   │   │   └── config
│   │   ├── extensions
│   │   │   ├── README.md
│   │   │   └── filebeat
│   │   ├── kibana
│   │   │   ├── Dockerfile
│   │   │   └── config
│   │   ├── run_env
│   │   └── setup
│   │       ├── Dockerfile
│   │       ├── entrypoint.sh
│   │       ├── helpers.sh
│   │       └── roles
│   ├── grafana
│   │   ├── config
│   │   │   ├── dashboards.yaml
│   │   │   └── datasources.yaml
│   │   └── dashboards
│   │       └── 1860_rev31.json
│   ├── prometheus
│   │   └── config
│   │       ├── alert-rules.yml
│   │       └── prometheus.yml
│   └── setup.yaml
├── pytest.ini
├── scripts
│   ├── bootstrap.sh
│   └── cleanup.sh
├── terraform
│   ├── main.tf
│   ├── mlops.tfvars
│   ├── outputs.tf
│   ├── terraform.tfstate
│   ├── terraform.tfstate.backup
│   └── variables.tf
└── tests
    ├── __init__.py
    └── test_main.py
```