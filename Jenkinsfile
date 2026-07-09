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

        stage('Checkout') {
            steps {
                echo 'Checking out source code from GitHub...'
                checkout scm
            }
        }

        stage('Unit Tests & Coverage') {
            steps {
                echo 'Running pytest with coverage...'
                sh '''
                    python3 -m pip install --quiet --break-system-packages \
                        pytest pytest-cov -r requirements.txt
                    python3 -m pytest tests/ \
                        -v \
                        --tb=short \
                        --cov=src \
                        --cov-report=xml
                '''
            }
        }

        stage('Quality Checks') {
            parallel {

                stage('SonarQube Analysis') {
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
                                -t ${IMAGE_NAME}:latest .
                        '''
                    }
                }
            }
        }

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

        stage('Deploy to K3s') {
            steps {
                echo 'Deploying to Production Server via Ansible...'
                withCredentials([sshUserPrivateKey(
                    credentialsId: 'prod-server-ssh-key',
                    keyFileVariable: 'SSH_KEY'
                )]) {
                    sh '''
                        scp -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            -r ansible \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP}:/home/ubuntu/

                        scp -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            -r k8s \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP}:/home/ubuntu/

                        ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no \
                            ${PROD_SERVER_USER}@${PROD_SERVER_IP} \
                            "ansible-playbook /home/ubuntu/ansible/deploy.yml \
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
            sh "docker image rm ${IMAGE_NAME}:${IMAGE_TAG} || true"
            sh "docker image rm ${IMAGE_NAME}:latest || true"
            sh "rm -f coverage.xml || true"
        }
    }
}