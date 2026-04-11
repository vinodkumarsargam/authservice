pipeline {
    agent any

    environment {
        IMAGE_NAME = "manojkrishnappa/authservice:${GIT_COMMIT}"
    }

    stages {

        stage('Git Checkout') {
            steps {
                git url: 'https://github.com/QuntamVector/authservice.git', branch: 'main'
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    printenv
                    docker build -t ${IMAGE_NAME} .
                '''
            }
        }

        stage('Login to Docker Hub') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'docker-hub-creds',
                    usernameVariable: 'DOCKER_USERNAME',
                    passwordVariable: 'DOCKER_PASSWORD'
                )]) {
                    sh "echo $DOCKER_PASSWORD | docker login -u $DOCKER_USERNAME --password-stdin"
                }
            }
        }

        stage('Push to Docker Hub') {
            steps {
                sh "docker push ${IMAGE_NAME}"
            }
        }

        stage('Update GitOps Deployment') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'github-creds',
                    usernameVariable: 'GIT_USERNAME',
                    passwordVariable: 'GIT_PASSWORD'
                )]) {
                    sh '''
                        if [ -d "gitops" ]; then
                            echo "gitops directory exists. Removing it..."
                            rm -rf gitops
                        fi
                        git clone https://$GIT_USERNAME:$GIT_PASSWORD@github.com/QuntamVector/GitOps.git gitops
                        cd gitops/base/authservice/

                        git config user.email "jenkins@ci.com"
                        git config user.name "jenkins"

                        # Update image tag
                        sed -i "s|image: .*authservice.*|image: ${IMAGE_NAME}|g" deployment.yaml

                        git add .
                        git commit -m "Update authservice image to ${IMAGE_NAME}"
                        git push origin main
                    '''
                }
            }
        }

    }

    post {
        always {
            sh "docker rmi ${IMAGE_NAME} || true"
            sh "docker logout || true"
        }
        success {
            echo "Build and push successful: ${IMAGE_NAME}"
        }
        failure {
            echo "Pipeline failed. Check the logs above."
        }
    }
}
