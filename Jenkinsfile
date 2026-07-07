pipeline {
    agent any

    environment {
        DOCKER_HUB_USER   = 'lordibe'
        IMAGE_NAME        = 'lordibe/rag-chatbot'
        IMAGE_TAG         = "${BUILD_NUMBER}"
        SONAR_HOST_URL    = 'http://54.90.233.69:9000'
        SONAR_PROJECT_KEY = 'rag-chatbot'
        PROD_SERVER_IP    = '172.31.35.255'
        PROD_SERVER_USER  = 'ubuntu'
    }

    stages {

        stage('Checkout') {
            steps {
                echo 'Checking out source code from GitHub...'
                checkout scm
            }
        }

        stage('Static Analysis') {
            steps {
                echo 'Running SonarQube static analysis...'
                withCredentials([string(credentialsId: 'sonarqube-token', variable: 'SONAR_TOKEN')]) {
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

        stage('Docker Build') {
            steps {
                echo "Building Docker image ${IMAGE_NAME}:${IMAGE_TAG}..."
                sh '''
                    docker build \
                        -t ${IMAGE_NAME}:${IMAGE_TAG} \
                        -t ${IMAGE_NAME}:latest \
                        .
                '''
            }
        }

        stage('Security Scan') {
            steps {
                echo 'Scanning Docker image with Trivy...'
                sh '''
                    trivy image \
                        --exit-code 1 \
                        --severity HIGH,CRITICAL \
                        --no-progress \
                        --format table \
                        ${IMAGE_NAME}:${IMAGE_TAG}
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                echo 'Running pytest unit tests inside Docker container...'
                sh '''
                    docker run --rm \
                        -e CHROMA_DB_PATH=/tmp/chroma_test \
                        -e DATA_DIR=/app/data \
                        -e GROQ_API_KEY=test_key_not_used_in_tests \
                        --workdir /app/src \
                        --entrypoint python \
                        ${IMAGE_NAME}:${IMAGE_TAG} \
                        -m pytest ../tests/ -v --tb=short
                '''
            }
        }

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

        stage('Deploy') {
            steps {
                echo 'Deploying to Production Server via Ansible...'
                withCredentials([sshUserPrivateKey(
                    credentialsId: 'prod-server-ssh-key',
                    keyFileVariable: 'SSH_KEY'
                )]) {
                    sh '''
                        scp -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            ansible/deploy.yml \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP}:/home/ubuntu/

                        scp -i ${SSH_KEY} -o StrictHostKeyChecking=no -r \
                            k8s/ \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP}:/home/ubuntu/

                        ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP} \
                            "ansible-playbook /home/ubuntu/deploy.yml \
                             -e image_tag=${IMAGE_TAG} \
                             -e docker_hub_user=${DOCKER_HUB_USER}"
                    '''
                }
            }
        }

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
            sh "docker rmi ${IMAGE_NAME}:${IMAGE_TAG} || true"
            sh "docker rmi ${IMAGE_NAME}:latest || true"
        }
    }
}