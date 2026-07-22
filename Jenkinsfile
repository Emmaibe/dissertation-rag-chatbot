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
        // Multi-stage build: compiler tooling stripped from final image,
        // reducing attack surface and Trivy-reportable CVEs.
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
        // Runs pytest tests inside the built image as the app user.
        // Tests never call the LLM so no real GROQ_API_KEY is needed.
        stage('Unit Tests') {
            steps {
                echo 'Running pytest inside Docker container...'
                sh """
                    TEST_CONTAINER="rag-chatbot-test-${BUILD_NUMBER}"
                    docker rm -f "\${TEST_CONTAINER}" || true

                    docker create \
                        --name "\${TEST_CONTAINER}" \
                        -e CHROMA_DB_PATH=/tmp/chroma_test \
                        -e DATA_DIR=/app/data \
                        -e GROQ_API_KEY=test_key_not_used_in_tests \
                        -e PYTHONPATH=/app/src \
                        --user app \
                        --workdir /app \
                        ${IMAGE_NAME}:${IMAGE_TAG} \
                        python -m pytest tests/ -v --tb=short \
                            --cov=src \
                            --cov-report=term-missing \
                            --cov-report=xml:/tmp/coverage.xml

                    docker start -a "\${TEST_CONTAINER}"
                    docker cp "\${TEST_CONTAINER}":/tmp/coverage.xml coverage.xml
                    docker rm "\${TEST_CONTAINER}"

                    python3 -c "from pathlib import Path; p=Path('coverage.xml'); p.write_text(p.read_text().replace('<source>/app/src</source>', '<source>src</source>'))"
                """
            }
            post {
                always {
                    sh "docker rm -f rag-chatbot-test-${BUILD_NUMBER} || true"
                }
            }
        }

        // ── Stage 4: Static Analysis + Quality Gate (SonarQube) ───────────
        // Analyses src/ for bugs, vulnerabilities, and code smells.
        // Polls the SonarQube Quality Gate API after scanning — pipeline
        // FAILS if the gate status is not OK. This is a genuine blocking
        // gate, not just a reporting step.
        // For the "without security controls" demonstration: comment out
        // the Quality Gate polling block below.
        stage('Static Analysis') {
            steps {
                echo 'Running SonarQube static analysis...'
                withCredentials([string(credentialsId: 'sonarqube-token',
                                        variable: 'SONAR_TOKEN')]) {
                    sh '''
                        sonar-scanner \
                            -Dsonar.projectKey=${SONAR_PROJECT_KEY} \
                            -Dsonar.sources=src \
                            -Dsonar.tests=tests \
                            -Dsonar.python.coverage.reportPaths=coverage.xml \
                            -Dsonar.python.version=3.12 \
                            -Dsonar.host.url=${SONAR_HOST_URL} \
                            -Dsonar.token=${SONAR_TOKEN}
                    '''

                    // ── Quality Gate check ─────────────────────────────────
                    // Wait for SonarQube to compute the gate result, then
                    // poll the API and fail the pipeline if status != OK.
                    sh '''
                        echo "Waiting for SonarQube to compute Quality Gate result..."
                        sleep 15

                        GATE_STATUS=$(curl -sf -u "${SONAR_TOKEN}:" \
                            "${SONAR_HOST_URL}/api/qualitygates/project_status?projectKey=${SONAR_PROJECT_KEY}" \
                            | python3 -c "import sys,json; print(json.load(sys.stdin)['projectStatus']['status'])")

                        echo "Quality Gate status: ${GATE_STATUS}"

                        if [ "${GATE_STATUS}" != "OK" ]; then
                            echo "SonarQube Quality Gate FAILED — blocking deployment."
                            echo "Fix the reported issues and push again."
                            exit 1
                        fi

                        echo "SonarQube Quality Gate PASSED — proceeding to security scan."
                    '''
                }
            }
        }

        // ── Stage 5: Security Scan (Trivy) ────────────────────────────────
        // Scans the built image for HIGH and CRITICAL CVEs that have fixes.
        // --exit-code 1: pipeline FAILS if fixable vulnerabilities are found.
        // For the "without security controls" demonstration: change to
        // --exit-code 0 so Trivy reports but does not block.
        stage('Security Scan') {
            steps {
                echo 'Scanning Docker image with Trivy...'
                sh '''
                    trivy image \
                        --severity HIGH,CRITICAL \
                        --ignore-unfixed \
                        --exit-code 1 \
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
