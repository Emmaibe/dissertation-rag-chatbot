pipeline {
    agent any

    environment {
        DOCKER_HUB_USER   = 'lordibe'
        IMAGE_NAME        = 'lordibe/rag-chatbot'
        IMAGE_TAG         = "${BUILD_NUMBER}"
        SONAR_HOST_URL    = 'http://54.204.237.137:9000'
        SONAR_PROJECT_KEY = 'rag-chatbot'
        PROD_SERVER_IP    = '172.31.35.255'
        PROD_SERVER_USER  = 'ubuntu'
    }

    stages {

        // ── Stage 1: Checkout ──────────────────────────────────────────────
        stage('Checkout') {
            steps {
                echo 'Checking out source code from GitHub...'
                checkout scm
            }
        }

        // ── Stage 2: Docker Build ──────────────────────────────────────────
        stage('Docker Build') {
            steps {
                echo "Building Docker image ${IMAGE_NAME}:${IMAGE_TAG}..."
                sh '''
                    docker build \
                        -t ${IMAGE_NAME}:${IMAGE_TAG} \
                        -t ${IMAGE_NAME}:latest .
                '''
            }
        }

        // ── Stage 3: Unit Tests ───────────────────────────────────────────
        // Runs 13 pytest tests inside the built image as the app user.
        // Tests never call the LLM so no real GROQ_API_KEY is needed.
        stage('Unit Tests') {
            steps {
                echo 'Running pytest inside Docker container...'
                sh """
                    docker run --rm \
                        -e CHROMA_DB_PATH=/tmp/chroma_test \
                        -e DATA_DIR=/app/data \
                        -e GROQ_API_KEY=test_key_not_used_in_tests \
                        -e PYTHONPATH=/app/src \
                        --user app \
                        --workdir /app \
                        ${IMAGE_NAME}:${IMAGE_TAG} \
                        python -m pytest tests/ -v --tb=short
                """
            }
        }

        // ── Stage 4: Static Analysis (SonarQube) ──────────────────────────
        stage('Static Analysis') {
            steps {
                echo 'Running SonarQube static analysis...'
                withCredentials([string(credentialsId: 'sonarqube-token',
                                        variable: 'SONAR_TOKEN')]) {
                    sh '''
                        sonar-scanner \
                            -Dsonar.projectKey=${SONAR_PROJECT_KEY} \
                            -Dsonar.sources=src \
                            -Dsonar.python.version=3.12 \
                            -Dsonar.host.url=${SONAR_HOST_URL} \
                            -Dsonar.token=${SONAR_TOKEN}
                    '''
                }
            }
        }

        // ── Stage 5: Security Scan (Trivy) ────────────────────────────────
        // Reports CVEs but does not block (exit-code 0) for the baseline run.
        // Switch to exit-code 1 for the "with security controls" demonstration.
        stage('Security Scan') {
            steps {
                echo 'Scanning Docker image with Trivy...'
                sh '''
                    trivy image \
                        --severity HIGH,CRITICAL \
                        --ignore-unfixed \
                        --exit-code 0 \
                        --no-progress \
                        --format table \
                        ${IMAGE_NAME}:${IMAGE_TAG}
                '''
            }
        }

        // ── Stage 6: Push Image ───────────────────────────────────────────
        stage('Push Image') {
            steps {
                echo "Pushing ${IMAGE_NAME}:${IMAGE_TAG} to Docker Hub..."
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-credentials',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                        echo "${DOCKER_PASS}" | docker login \
                            -u "${DOCKER_USER}" --password-stdin
                        docker push ${IMAGE_NAME}:${IMAGE_TAG}
                        docker push ${IMAGE_NAME}:latest
                    '''
                }
            }
        }

        // ── Stage 7: Deploy to K3s ────────────────────────────────────────
        // Ansible handles: namespace, PVC, ConfigMap, Secret, Deployment,
        // Service, rolling restart, rollout wait, ingest, and pod status.
        stage('Deploy to K3s') {
            steps {
                echo 'Deploying to Production Server via Ansible...'
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'prod-server-ssh-key',
                        keyFileVariable: 'SSH_KEY'
                    ),
                    file(
                        credentialsId: 'rag-chatbot-env',
                        variable: 'ENV_FILE'
                    )
                ]) {
                    sh """
                        scp -i \${SSH_KEY} -o StrictHostKeyChecking=no \
                            -r ansible \
                            \${PROD_SERVER_USER}@\${PROD_SERVER_IP}:/home/ubuntu/

                        scp -i \${SSH_KEY} -o StrictHostKeyChecking=no \
                            -r k8s \
                            \${PROD_SERVER_USER}@\${PROD_SERVER_IP}:/home/ubuntu/

                        scp -i \${SSH_KEY} -o StrictHostKeyChecking=no \
                            \${ENV_FILE} \
                            \${PROD_SERVER_USER}@\${PROD_SERVER_IP}:/home/ubuntu/.env

                        ssh -i \${SSH_KEY} -o StrictHostKeyChecking=no \
                            \${PROD_SERVER_USER}@\${PROD_SERVER_IP} \
                            'ansible-playbook /home/ubuntu/ansible/deploy.yml \
                             -e image_tag=${IMAGE_TAG} \
                             -e docker_hub_user=${DOCKER_HUB_USER}'
                    """
                }
            }
        }

        // ── Stage 8: Verify Deployment ────────────────────────────────────
        // Ansible already ingested the corpus and confirmed pods are running.
        // This stage does a final health check to confirm the API is healthy.
        stage('Verify Deployment') {
            steps {
                echo 'Verifying deployment on Production Server...'
                withCredentials([sshUserPrivateKey(
                    credentialsId: 'prod-server-ssh-key',
                    keyFileVariable: 'SSH_KEY'
                )]) {
                    sh """
                        ssh -i \${SSH_KEY} -o StrictHostKeyChecking=no \
                            \${PROD_SERVER_USER}@\${PROD_SERVER_IP} \
                            'sudo kubectl get pods -n rag-chatbot && \
                             curl -s http://localhost:30080/health'
                    """
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline SUCCESS. Image ${IMAGE_NAME}:${IMAGE_TAG} is live on K3s."
        }
        failure {
            echo 'Pipeline FAILED. Check the stage output above for details.'
        }
        always {
            sh "docker image rm ${IMAGE_NAME}:${IMAGE_TAG} || true"
            sh "docker image rm ${IMAGE_NAME}:latest || true"
        }
    }
}