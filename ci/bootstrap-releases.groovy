// Run once in the administrator Script Console after creating github-release-token.
import hudson.plugins.git.BranchSpec
import hudson.plugins.git.GitSCM
import hudson.plugins.git.UserRemoteConfig
import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import org.jenkinsci.plugins.workflow.job.WorkflowJob

def jenkins = Jenkins.get()
def name = 'desktop-pdf-releases'
def job = jenkins.getItem(name)
if (job == null) { job = jenkins.createProject(WorkflowJob, name) }
assert job instanceof WorkflowJob: 'The existing item is not a Pipeline job'
def scm = new GitSCM(
    [new UserRemoteConfig('https://github.com/CobbiFantom/desktop-jenkins.git', null, null, null)],
    [new BranchSpec('*/main')], false, [], null, null, []
)
def definition = new CpsScmFlowDefinition(scm, 'Jenkinsfile.releases')
definition.setLightweight(true)
job.setDefinition(definition)
job.setDescription('Published GitHub releases -> exact tag builds on macOS and Linux -> release ZIP assets. Checks every two minutes.')
job.save()
job.scheduleBuild2(0)
println 'Configured and scheduled: ' + job.fullName
