// Run in the Jenkins administrator Script Console after pushing main.
import hudson.plugins.git.BranchSpec
import hudson.plugins.git.GitSCM
import hudson.plugins.git.UserRemoteConfig
import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import org.jenkinsci.plugins.workflow.job.WorkflowJob

def jenkins = Jenkins.get()
def name = 'desktop-pdf-translator'
def job = jenkins.getItem(name)
if (job == null) {
    job = jenkins.createProject(WorkflowJob, name)
}
assert job instanceof WorkflowJob: 'The existing item is not a Pipeline job'
def scm = new GitSCM(
    [new UserRemoteConfig('https://github.com/CobbiFantom/desktop-jenkins.git', null, null, null)],
    [new BranchSpec('*/main')], false, [], null, null, []
)
def definition = new CpsScmFlowDefinition(scm, 'Jenkinsfile')
definition.setLightweight(true)
job.setDefinition(definition)
job.setDescription('Git main -> tests -> parallel macOS/Linux builds -> downloadable ZIP artifacts. Git polling is configured in Jenkinsfile.')
job.save()
println 'Configured job: ' + job.fullName
// First build installs the polling trigger declared in Jenkinsfile.
job.scheduleBuild2(0)
println 'Initial build scheduled'
