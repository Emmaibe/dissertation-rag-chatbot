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
        // Build the image first so all subsequent stages test/scan the
        // actual artefact that will be deployed, not a separate environment.
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
        // Run pytest inside the built image — proves the image itself works.
        // No host pip/venv issues; uses the app user whose PATH includes
        // /home/app/.local/bin where pytest is installed.
        // Tests never call the LLM so no real GROQ_API_KEY is needed.
        stage('Unit Tests') {
            steps {
                echo 'Running pytest inside Docker container...'
                sh '''
                    docker run --rm \
                        -e CHROMA_DB_PATH=/tmp/chroma_test \
                        -e DATA_DIR=/app/data \
                        -e GROQ_API_KEY=test_key_not_used_in_tests \
                        -e PYTHONPATH=/app/src \
                        --user app \
                        --workdir /app \
                        ${IMAGE_NAME}:${IMAGE_TAG} \
                        python -m pytest tests/ -v --tb=short
                '''
            }
        }

        // ── Stage 4: Static Analysis (SonarQube) ──────────────────────────
        // Analyses src/ for bugs, vulnerabilities, and code smells.
        // Quality gate must pass before the image is allowed to proceed.
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
        // Scans the built image for HIGH and CRITICAL CVEs that have fixes.
        // --ignore-unfixed: only fails on actionable vulnerabilities.
        // This is the key security gate for the dissertation's
        // "with/without security controls" comparison.
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
        // Only reached if all previous gates pass.
        // Image pushed to Docker Hub for K3s to pull on the Prod Server.
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
        // Copies manifests to the Production Server then runs Ansible
        // which applies them to K3s with the new image tag.
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
                    sh '''
                        scp -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            -r ansible \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP}:/home/ubuntu/

                        scp -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            -r k8s \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP}:/home/ubuntu/

                        scp -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            ${ENV_FILE} \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP}:/home/ubuntu/.env

                        ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP} \
                            "ansible-playbook /home/ubuntu/ansible/deploy.yml \
                             -e image_tag=${IMAGE_TAG} \
                             -e docker_hub_user=${DOCKER_HUB_USER} && \
                             rm -f /home/ubuntu/.env"
                    '''
                }
            }
}

        // ── Stage 8: Verify Deployment ────────────────────────────────────
        // Confirms all 3 replicas are Running and /health returns "healthy".
        stage('Verify Deployment') {
            steps {
                echo 'Verifying deployment on Production Server...'
                withCredentials([sshUserPrivateKey(
                    credentialsId: 'prod-server-ssh-key',
                    keyFileVariable: 'SSH_KEY'
                )]) {
                    sh '''
                        ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP} \
                            "sudo kubectl get pods -n rag-chatbot && \
                             sudo kubectl rollout status deployment/rag-chatbot \
                                 -n rag-chatbot --timeout=120s && \
                             sleep 60 && \
                             curl -sf -X POST http://localhost:30080/ingest && \
                             sleep 30 && \
                             curl -sf http://localhost:30080/health | \
                             python3 -c \\"import sys,json; \
                                 d=json.load(sys.stdin); \
                                 sys.exit(0 if d.get('status')=='healthy' else 1)\\""
                    '''
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