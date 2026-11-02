// Run once in the Jenkins administrator Script Console.
// Connection secrets stay in Jenkins home and must never be added to Git.
import hudson.model.Node
import hudson.slaves.DumbSlave
import hudson.slaves.JNLPLauncher
import hudson.slaves.RetentionStrategy
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import jenkins.model.Jenkins

def jenkins = Jenkins.get()
def definitions = [
    macos: ['/Users/cobbi/jenkins-agent', 'macos arm64 desktop'],
    linux: ['/home/jenkins/agent', 'linux amd64 desktop'],
]
def secretDirectory = jenkins.rootDir.toPath().resolve('agent-bootstrap')
Files.createDirectories(secretDirectory)
Files.setPosixFilePermissions(secretDirectory, PosixFilePermissions.fromString('rwx------'))
definitions.each { name, settings ->
    def launcher = new JNLPLauncher()
    launcher.setWebSocket(true)
    def node = jenkins.getNode(name)
    if (node == null) {
        node = new DumbSlave(name, settings[0], launcher)
        node.setNumExecutors(1)
        node.setMode(Node.Mode.EXCLUSIVE)
        node.setLabelString(settings[1])
        node.setRetentionStrategy(new RetentionStrategy.Always())
        jenkins.addNode(node)
    } else {
        assert node.getRemoteFS() == settings[0]: "Unexpected existing node: ${name}"
        node.setLauncher(launcher)
        node.save()
    }
    def secretPath = secretDirectory.resolve(name + '.secret')
    Files.writeString(secretPath, node.toComputer().getJnlpMac())
    Files.setPosixFilePermissions(secretPath, PosixFilePermissions.fromString('rw-------'))
    println "Ready: ${name}; labels=${node.labelString}; executors=${node.numExecutors}"
}
def required = ['workflow-job', 'workflow-cps', 'pipeline-model-definition', 'git', 'junit', 'timestamper']
def missing = required.findAll { jenkins.pluginManager.getPlugin(it) == null }
println "Missing pipeline plugins: ${missing}"
