pipeline {
    agent any

    options{
        // Max number of build logs to keep and days to keep
        buildDiscarder(logRotator(numToKeepStr: '5', daysToKeepStr: '5'))
        // Enable timestamp at each job in the pipeline
        timestamps()
    }

    environment{
        registry = 'minhtuan172/nbiot-detector-app'
        registryCredential = 'docker'
        // Helm chart details
        helmChartPath = './kubernetes/helm/app-nbiot-detector' // Path to your chart directory
        helmReleaseName = 'app-nbiot-detector'
        helmValuesFile = "${helmChartPath}/values.yaml"
        // Kubernetes namespace (optional, defaults to 'default' if not specified in kubeconfig or command)
        kubernetesNamespace = 'default'
    }

    stages {
        stage('Test') {
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
                    pip install --no-cache-dir --upgrade pip
                    pip install --no-cache-dir -r requirements.txt
                    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
                    echo "Running tests"
                    cd ..
                    pytest
                    echo "Deactivating virtual environment"
                    deactivate
                '''
            }
        }
        stage('Build') {
            agent {
                kubernetes {
                    label 'docker-build-environment'
                    defaultContainer 'docker'
                }
            }
            steps {
                echo "--- Build Stage: Entering steps ---"
                script {
                    // Attempt to pull the latest image for caching, but don't fail if it doesn't exist
                    try {
                        sh "docker pull ${registry}:latest || true"
                    } catch (Exception e) {
                        echo "Could not pull latest image for cache, proceeding without it. Error: ${e.getMessage()}"
                    }

                    echo 'Building image for deployment..'
                    // Add --cache-from to the docker.build command
                    dockerImage = docker.build registry + ":$BUILD_NUMBER", "--cache-from ${registry}:latest ."

                    echo 'Pushing image to dockerhub..'
                    docker.withRegistry( '', registryCredential ) {
                        dockerImage.push()
                        dockerImage.push('latest')
                    }
                }
            }
        }
        stage('Deploy') {
             agent {
                kubernetes {
                    label 'k8s-deploy-agent'
                    defaultContainer 'tools' // this container have kubectl and helm
                }
            }
            environment {
                KUBE_DEPLOYMENT_NAME = "${env.helmReleaseName}"
                APP_NAMESPACE = "${env.kubernetesNamespace}"
            }
            steps {
                script {
                    echo "--- KUBERNETES ENVIRONMENT DIAGNOSTICS ---"
                    sh 'echo "Attempting to unset KUBECONFIG to ensure in-cluster config is used."'
                    sh 'unset KUBECONFIG || true'
                    sh 'echo "--- Relevant KUBE environment variables ---"'
                    sh 'env | grep KUBE || echo "No KUBE* env vars found"'
                    sh 'echo "--- Service Account Token (if present) ---"'
                    sh 'ls -l /var/run/secrets/kubernetes.io/serviceaccount/ || echo "Service account directory not found or not listable"'
                    sh 'echo "--- Current kubectl config view ---"'
                    sh "kubectl config view"
                    echo "------------------------------------------"

                    echo "Deploying ${helmReleaseName} to namespace ${APP_NAMESPACE} using Helm chart from ${helmChartPath}..."
                    echo "Image to be deployed: ${registry}:${env.BUILD_NUMBER}"

                    try {
                        sh "helm lint ${helmChartPath}"

                        // Helm upgrade command
                        sh """
                            helm upgrade --install ${helmReleaseName} ${helmChartPath} \
                                -n ${APP_NAMESPACE} \
                                -f ${helmValuesFile} \
                                --set image.repository=${registry} \
                                --set image.tag=${env.BUILD_NUMBER} \
                                --atomic \
                                --timeout 10m \
                                --wait \
                                --debug
                        """

                        echo "Helm upgrade of ${helmReleaseName} in namespace ${APP_NAMESPACE} initiated successfully."
                        echo "Waiting for rollout to complete for deployment/${KUBE_DEPLOYMENT_NAME} in namespace ${APP_NAMESPACE}..."

                        sh "kubectl rollout status deployment/${KUBE_DEPLOYMENT_NAME} -n ${APP_NAMESPACE} --timeout=5m"
                        echo "Deployment ${KUBE_DEPLOYMENT_NAME} successfully rolled out in namespace ${APP_NAMESPACE}."

                        echo "Running application-specific health checks (if any)..."
                        // Example: sh "./run-my-health-checks.sh ${APP_NAMESPACE} ${helmReleaseName}"

                        timeout(time: 15, unit: 'MINUTES') {
                            def userInput = input(
                                id: 'confirmDeployment',
                                message: "Deployment of ${helmReleaseName} (Image: ${registry}:${env.BUILD_NUMBER}) in namespace ${APP_NAMESPACE} seems successful. Proceed or Rollback?",
                                parameters: [
                                    [$class: 'ChoiceParameterDefinition', choices: 'Proceed\nRollback', name: 'ACTION']
                                ]
                            )
                            if (userInput == 'Rollback') {
                                echo "Manual rollback initiated for ${helmReleaseName} in namespace ${APP_NAMESPACE}."
                                sh "helm rollback ${helmReleaseName} 0 -n ${APP_NAMESPACE}" // 0 rolls back to previous revision
                                currentBuild.result = 'ABORTED' // Mark build as aborted due to manual rollback
                                error("Deployment manually rolled back by user.")
                            } else {
                                echo "Deployment confirmed by user."
                            }
                        }

                    } catch (err) {
                        echo "Deployment failed for ${helmReleaseName} in namespace ${APP_NAMESPACE}. Error: ${err.getMessage()}"
                        if (err.getMessage().contains("localhost:8080") || err.getMessage().contains("connection refused")) {
                            echo "CRITICAL ERROR: Agent is still trying to connect to localhost:8080. This means it's NOT correctly using the in-cluster Kubernetes configuration. Check Jenkins agent setup (Kubernetes plugin, pod templates) to ensure this stage runs as a pod *inside* your Minikube cluster."
                        }
                        echo "Attempting automatic rollback..."
                        // These helm commands will also fail if the connection issue persists
                        sh "helm history ${helmReleaseName} -n ${APP_NAMESPACE} || echo 'helm history command failed (may be due to connection issue).'"
                        sh "helm rollback ${helmReleaseName} 0 -n ${APP_NAMESPACE} || echo 'Rollback to previous revision failed or no previous revision found (may be due to connection issue).'"
                        sh "helm status ${helmReleaseName} -n ${APP_NAMESPACE} || echo 'helm status command failed (may be due to connection issue).'"
                        error("Deployment failed and rollback attempted for ${helmReleaseName}.")
                    }
                }
            }
            post {
                always {
                    echo "Cleaning up deployment step..."
                }
            }
        }
    }
}