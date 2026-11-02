pipeline {
    // The controller schedules work; builds run on the two labelled agents.
    agent none
    parameters {
        string(name: 'RELEASE_TAG', defaultValue: '',
               description: 'Published GitHub release tag; empty means ordinary main CI')
        string(name: 'MACOS_PYTHON', defaultValue: '/opt/homebrew/bin/python3.13',
               description: 'Python 3.10-3.13 on the macos agent; absolute path is recommended')
        string(name: 'LINUX_PYTHON', defaultValue: 'python3',
               description: 'Python 3.10-3.13 on the linux agent')
    }
    options {
        timestamps()
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    environment { QT_QPA_PLATFORM = 'offscreen' }
    // The controller is private, so Git polling does not require a public webhook.
    triggers { pollSCM('H/2 * * * *') }
    stages {
        stage('Resolve release source') {
            when { expression { return params.RELEASE_TAG?.trim() } }
            agent { label 'linux' }
            steps {
                dir('ci-release-tools') {
                    deleteDir()
                    checkout scm
                    // Use trusted main tooling even when an older tag lacks the publisher.
                    stash name: 'release-tools', includes: 'scripts/github_release.py'
                    withCredentials([string(credentialsId: 'github-release-token', variable: 'GITHUB_TOKEN')]) {
                        script {
                            env.RELEASE_COMMIT = sh(returnStdout: true, script: '''
                                set +x
                                python3 scripts/github_release.py resolve "$RELEASE_TAG"
                            ''').trim()
                            if (!(env.RELEASE_COMMIT ==~ /[0-9a-f]{40}/)) {
                                error('Invalid release source commit')
                            }
                            echo "Building release ${params.RELEASE_TAG} at ${env.RELEASE_COMMIT}"
                        }
                    }
                }
            }
        }
        stage('Build macOS and Linux') {
            matrix {
                axes {
                    axis {
                        name 'PLATFORM'
                        values 'macos', 'linux'
                    }
                }
                agent { label "${PLATFORM}" }
                environment {
                    PYTHON = "${PLATFORM == 'macos' ? params.MACOS_PYTHON : params.LINUX_PYTHON}"
                }
                options {
                    // Includes waiting for an offline/busy agent.
                    timeout(time: 30, unit: 'MINUTES')
                }
                // No failFast: let the other platform finish and archive its ZIP.
                stages {
                    stage('Checkout') {
                        steps {
                            dir("ci-${PLATFORM}") {
                                // Only this platform's Jenkins work directory is cleared.
                                deleteDir()
                                script {
                                    if (env.RELEASE_COMMIT) {
                                        checkout changelog: false, poll: false, scm: [
                                            $class: 'GitSCM',
                                            branches: [[name: env.RELEASE_COMMIT]],
                                            userRemoteConfigs: [[
                                                url: 'https://github.com/CobbiFantom/desktop-jenkins.git',
                                                refspec: '+refs/heads/main:refs/remotes/origin/main +refs/tags/*:refs/tags/*'
                                            ]],
                                            extensions: [[$class: 'CloneOption', noTags: false, shallow: false]]
                                        ]
                                        def actual = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
                                        if (actual != env.RELEASE_COMMIT) { error('Release checkout mismatch') }
                                    } else {
                                        checkout scm
                                    }
                                }
                            }
                        }
                    }
                    stage('Install') {
                        steps {
                            dir("ci-${PLATFORM}") {
                                sh '''
                                    set -eu
                                    case "$PLATFORM:$(uname -s)" in
                                        macos:Darwin|linux:Linux) ;;
                                        *) echo "Agent OS does not match label $PLATFORM" >&2; exit 1 ;;
                                    esac
                                    "$PYTHON" -c 'import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 13), "Use Python 3.10-3.13"'
                                    "$PYTHON" -m venv .venv
                                    .venv/bin/python -m pip install -r requirements-lock.txt
                                '''
                            }
                        }
                    }
                    stage('Test') {
                        steps {
                            dir("ci-${PLATFORM}") {
                                sh '''
                                    set -eu
                                    .venv/bin/python -m pytest --junitxml="reports/tests-$PLATFORM.xml" --junit-prefix="$PLATFORM"
                                '''
                            }
                        }
                        post {
                            always {
                                dir("ci-${PLATFORM}") {
                                    junit testResults: "reports/tests-${PLATFORM}.xml"
                                }
                            }
                        }
                    }
                    stage('Build desktop') {
                        steps {
                            dir("ci-${PLATFORM}") {
                                sh '''
                                    set -eu
                                    .venv/bin/python -m PyInstaller --noconfirm --clean PDFUkrainian.spec
                                '''
                            }
                        }
                    }
                    stage('Smoke test, package and archive') {
                        steps {
                            dir("ci-${PLATFORM}") {
                                sh '''
                                    set -eu
                                    if [ "$PLATFORM" = macos ]; then
                                        dist/PDFUkrainian.app/Contents/MacOS/PDFUkrainian --smoke-test
                                    else
                                        # Exercise the actual Linux window backend, not only offscreen Qt.
                                        QT_QPA_PLATFORM=xcb xvfb-run -a dist/PDFUkrainian/PDFUkrainian --smoke-test
                                    fi
                                    .venv/bin/python scripts/package.py
                                '''
                                // Archive here, not in global post-success: the other
                                // platform may have failed while this one succeeded.
                                archiveArtifacts artifacts: 'dist/PDFUkrainian-*.zip', fingerprint: true
                                script {
                                    if (env.RELEASE_COMMIT) {
                                        stash name: "release-${PLATFORM}", includes: 'dist/PDFUkrainian-*.zip'
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        stage('Publish GitHub release') {
            when { expression { return env.RELEASE_COMMIT } }
            agent { label 'linux' }
            steps {
                dir('ci-release-publish') {
                    deleteDir()
                    unstash 'release-tools'
                    unstash 'release-macos'
                    unstash 'release-linux'
                    withCredentials([string(credentialsId: 'github-release-token', variable: 'GITHUB_TOKEN')]) {
                        sh '''
                            set +x
                            python3 scripts/github_release.py publish "$RELEASE_TAG" "$RELEASE_COMMIT" dist
                        '''
                    }
                }
            }
        }
    }
}
