pipeline {
    agent any

    options{
        // Max number of build logs to keep and days to keep
        buildDiscarder(logRotator(numToKeepStr: '5', daysToKeepStr: '5'))
        // Enable timestamp at each job in the pipeline
        timestamps()
    }

    environment{
        DOCKER_IMAGE_NAME = 'minhtuan172/nbiot-detector-app'
        DOCKER_CREDENTIAL_ID = 'docker-jenkins'

        // Helm chart details
        helmChartPath = './kubernetes/helm/app-nbiot-detector' // Path to your chart directory
        helmReleaseName = 'app-nbiot-detector'
        helmValuesFile = "${helmChartPath}/values.yaml"
        // Kubernetes namespace (optional, defaults to 'default' if not specified in kubeconfig or command)
        kubernetesNamespace = 'default'

        appConfigRepo = 'git@github.com:sweetiu172/nbiot_detector_core.git'
        appConfigBranch = 'feat/init-project'

        gitCommit = sh(script: "git rev-parse --short HEAD", returnStdout: true).trim()
        dockerTag = "${env.BUILD_NUMBER}-${gitCommit}"
    }

    stages {
        stage('Unit Test') {
            when {
                anyOf {
                    changeset "app/**"
                    changeset "Jenkinsfile"
                }
            }
            agent {
                kubernetes {
                    label 'python-test-environment'
                    defaultContainer 'python'
                }
            }
            steps {
                echo 'Testing model correctness..'
                sh '''
                    cd app
                    python3 -m venv venv
                    echo "Activating virtual environment"
                    . venv/bin/activate 
                    echo "Installing packages into virtual environment"
                    pip install --no-cache-dir -r requirements.txt
                    pip install --no-cache-dir torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu
                    echo "Running tests"
                    cd ..
                    pytest
                    echo "Deactivating virtual environment"
                    deactivate
                '''
            }
        }
        stage('Build') {
            when {
                anyOf {
                    changeset "app/**"
                    changeset "Jenkinsfile"
                }
            }
            agent {
                kubernetes {
                    label 'docker-build-environment'
                    defaultContainer 'docker'
                }
            }
            steps {
                echo "--- Build Stage: Entering steps ---"
                dir('app') {
                    script {
                        def dockerImage = docker.build("${env.DOCKER_IMAGE_NAME}:${env.dockerTag}", "--cache-from ${env.DOCKER_IMAGE_NAME}:latest .")

                        // Use the full registry URL and credentials for pushing
                        docker.withRegistry( '', env.DOCKER_CREDENTIAL_ID) {
                            echo "Pushing image ${dockerImage.id} to registry..."
                            dockerImage.push()

                            echo "Tagging and pushing as 'latest'..."
                            dockerImage.push('latest')
                        }
                    }
                }
            }
        }
        stage('Update value in helm-chart') {
            when {
                anyOf {
                    changeset "app/**"
                    changeset "Jenkinsfile"
                }
            }
            agent {
                kubernetes {
                    label 'git-agent'
                    defaultContainer 'git'
                }
            }
            environment {
                APP_CONFIG_REPO = "${env.appConfigRepo}"
                APP_CONFIG_BRANCH = "${env.appConfigBranch}"
            }
            steps {
                script {
                    // Jenkins automatically uses the key file for authentication with git.
                    // We must add GitHub's host key to the known_hosts file to avoid interactive prompts.
                    sh """
                        #!/bin/bash
                        set -e

                        echo "Setting up SSH..."
                        mkdir -p ~/.ssh
                        cp -a /home/jenkins/.ssh/.  ~/.ssh
                        chmod 600 ~/.ssh/id_rsa
                        ssh-keyscan github.com >> ~/.ssh/known_hosts

                        echo "Configuring Git..."
                        git config --global user.email "jenkins@example.com"
                        git config --global user.name "Jenkins CI SA"

                        echo "Cloning repo..."
                        git clone ${APP_CONFIG_REPO} --branch ${APP_CONFIG_BRANCH}
                        cd ./nbiot_detector_core

                        echo "Modifying Helm values.yaml..."
                        sed -i "s/^  tag:.*/  tag: \\\"${env.dockerTag}\\\"/" ${helmValuesFile}
                        cat ${helmValuesFile}

                        echo "Committing and pushing changes..."
                        git add . 
                        git commit -m "CD: Update to version ${env.dockerTag}"
                        git push origin ${APP_CONFIG_BRANCH}
                    """
                }
            }
        }
        // stage('Deploy') {
        //      agent {
        //         kubernetes {
        //             label 'k8s-deploy-agent'
        //             defaultContainer 'tools' // this container have kubectl and helm
        //         }
        //     }
        //     environment {
        //         KUBE_DEPLOYMENT_NAME = "${env.helmReleaseName}"
        //         APP_NAMESPACE = "${env.kubernetesNamespace}"
        //     }
        //     steps {
        //         script {
        //             echo "--- KUBERNETES ENVIRONMENT DIAGNOSTICS ---"
        //             sh 'echo "Attempting to unset KUBECONFIG to ensure in-cluster config is used."'
        //             sh 'unset KUBECONFIG || true'
        //             sh 'echo "--- Relevant KUBE environment variables ---"'
        //             sh 'env | grep KUBE || echo "No KUBE* env vars found"'
        //             sh 'echo "--- Service Account Token (if present) ---"'
        //             sh 'ls -l /var/run/secrets/kubernetes.io/serviceaccount/ || echo "Service account directory not found or not listable"'
        //             sh 'echo "--- Current kubectl config view ---"'
        //             sh "kubectl config view"
        //             echo "------------------------------------------"

        //             echo "Deploying ${helmReleaseName} to namespace ${APP_NAMESPACE} using Helm chart from ${helmChartPath}..."
        //             echo "Image to be deployed: ${registry}:${env.BUILD_NUMBER}"

        //             try {
        //                 sh "helm lint ${helmChartPath}"

        //                 // Helm upgrade command
        //                 sh """
        //                     helm upgrade --install ${helmReleaseName} ${helmChartPath} \
        //                         -n ${APP_NAMESPACE} \
        //                         -f ${helmValuesFile} \
        //                         --set image.repository=${registry} \
        //                         --set image.tag=${env.BUILD_NUMBER} \
        //                         --atomic \
        //                         --timeout 10m \
        //                         --wait \
        //                         --debug
        //                 """

        //                 echo "Helm upgrade of ${helmReleaseName} in namespace ${APP_NAMESPACE} initiated successfully."
        //                 echo "Waiting for rollout to complete for deployment/${KUBE_DEPLOYMENT_NAME} in namespace ${APP_NAMESPACE}..."

        //                 sh "kubectl rollout status deployment/${KUBE_DEPLOYMENT_NAME} -n ${APP_NAMESPACE} --timeout=5m"
        //                 echo "Deployment ${KUBE_DEPLOYMENT_NAME} successfully rolled out in namespace ${APP_NAMESPACE}."

        //                 echo "Running application-specific health checks (if any)..."
        //                 // Example: sh "./run-my-health-checks.sh ${APP_NAMESPACE} ${helmReleaseName}"

        //                 timeout(time: 15, unit: 'MINUTES') {
        //                     def userInput = input(
        //                         id: 'confirmDeployment',
        //                         message: "Deployment of ${helmReleaseName} (Image: ${registry}:${env.BUILD_NUMBER}) in namespace ${APP_NAMESPACE} seems successful. Proceed or Rollback?",
        //                         parameters: [
        //                             [$class: 'ChoiceParameterDefinition', choices: 'Proceed\nRollback', name: 'ACTION']
        //                         ]
        //                     )
        //                     if (userInput == 'Rollback') {
        //                         echo "Manual rollback initiated for ${helmReleaseName} in namespace ${APP_NAMESPACE}."
        //                         sh "helm rollback ${helmReleaseName} 0 -n ${APP_NAMESPACE}" // 0 rolls back to previous revision
        //                         currentBuild.result = 'ABORTED' // Mark build as aborted due to manual rollback
        //                         error("Deployment manually rolled back by user.")
        //                     } else {
        //                         echo "Deployment confirmed by user."
        //                     }
        //                 }

        //             } catch (err) {
        //                 echo "Deployment failed for ${helmReleaseName} in namespace ${APP_NAMESPACE}. Error: ${err.getMessage()}"
        //                 if (err.getMessage().contains("localhost:8080") || err.getMessage().contains("connection refused")) {
        //                     echo "CRITICAL ERROR: Agent is still trying to connect to localhost:8080. This means it's NOT correctly using the in-cluster Kubernetes configuration. Check Jenkins agent setup (Kubernetes plugin, pod templates) to ensure this stage runs as a pod *inside* your Minikube cluster."
        //                 }
        //                 echo "Attempting automatic rollback..."
        //                 // These helm commands will also fail if the connection issue persists
        //                 sh "helm history ${helmReleaseName} -n ${APP_NAMESPACE} || echo 'helm history command failed (may be due to connection issue).'"
        //                 sh "helm rollback ${helmReleaseName} 0 -n ${APP_NAMESPACE} || echo 'Rollback to previous revision failed or no previous revision found (may be due to connection issue).'"
        //                 sh "helm status ${helmReleaseName} -n ${APP_NAMESPACE} || echo 'helm status command failed (may be due to connection issue).'"
        //                 error("Deployment failed and rollback attempted for ${helmReleaseName}.")
        //             }
        //         }
        //     }
        // }
    }
}