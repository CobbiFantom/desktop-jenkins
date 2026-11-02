# Jenkins deployment

The pipeline builds the trusted `main` branch of
`https://github.com/CobbiFantom/desktop-jenkins.git` on two permanent agents.
It does not execute pull requests from forks.

- Job: `desktop-pdf-translator`.
- Agent labels: `macos` and `linux`, one executor each, exclusive mode.
- Git polling: every two minutes, only new commits trigger a build.
- Delivery: ZIP packages and JUnit results on the Jenkins build page.
- Retention: ten builds. A successful platform archives its package even if the other platform fails.

The controller remains private. On the Mac, the existing SSH connection to
the VPS forwards `127.0.0.1:18080` to the controller's `127.0.0.1:8080`.
The Linux agent joins the existing `jenkins_default` Docker network.
No additional public port or Docker socket is exposed to the build agents.

## Mac service

Java 21 is installed through Homebrew. Per-user LaunchAgents start the
tunnel and the macOS inbound agent after login, and restart them if they exit:

```bash
launchctl print gui/$(id -u)/dev.desktop-jenkins.tunnel
launchctl print gui/$(id -u)/dev.desktop-jenkins.macos
```

Private configuration and logs are under `~/jenkins-agent/`.
The JVM connection arguments are kept in a file readable only by the local
user, so the connection secret is not placed in the process command line.
The Mac must be awake and connected to the network during macOS builds.

## Linux service on the VPS

Files are deployed to `/opt/desktop-jenkins/linux-agent/`:

```bash
cd /opt/desktop-jenkins/linux-agent
docker compose up -d --build
docker compose logs --tail 50
```

The image adds Python, Qt runtime libraries, fonts and build tools to the
official Jenkins inbound-agent image. The container has a dedicated workspace
volume, one CPU limit and a 1536 MiB memory limit. It restarts automatically.
The Linux package is also launched with the X11 Qt backend under Xvfb, so
missing GUI plugin libraries are detected even though the VPS has no monitor.
The private JVM argument file is outside the repository at
`/opt/desktop-jenkins/secrets/linux.args`, with read access for the agent user.

## Bootstrap

`bootstrap-agents.groovy` creates the two nodes and writes their connection
secrets to a private directory inside Jenkins home. Do not commit generated
secrets. `bootstrap-job.groovy` creates the Pipeline from SCM and schedules
the first run. These are administrator bootstrap scripts, not build steps.

After the first successful run, a `git push origin main` is enough to trigger
the next build within approximately two minutes while Jenkins is running.
Download packages from `desktop-pdf-translator -> build number -> Artifacts`.
These are portable application ZIPs; signing and OS installers are separate tasks.

## Automatic GitHub Releases

`desktop-pdf-releases` reads `Jenkinsfile.releases` from trusted `main` and checks
published GitHub releases every two minutes. Draft releases are ignored.
For each release missing packages it starts `desktop-pdf-translator` with
`RELEASE_TAG`. That job resolves the tag to an exact commit, checks out that
commit on both agents, runs tests and GUI smoke tests, and archives both ZIPs.
Only after both platforms succeed does it upload these assets to the existing
release, preserving its title and notes:

- `PDFUkrainian-Darwin-arm64.zip`
- `PDFUkrainian-Linux-x86_64.zip`

The pipeline/publishing helper comes from `main`; application code comes from
the release tag. This also supports old tags created before release automation.
Do not move published tags. The publisher checks the source commit again before
uploading. Existing assets bearing the same `git:<commit>` label are skipped on
retries; conflicting/unfinished assets require manual review and are never
overwritten or deleted automatically. Partial uploads can be resumed by running
the monitor or the build again. ZIP names match the two configured architectures;
update `scripts/github_release.py` if agents change architecture.

One-time setup:

1. Create a fine-grained GitHub token scoped to **only this repository**, with
   **Contents: Read and write** (Metadata read is implicit). No account permissions.
2. Save it in Jenkins as global **Secret text**, ID `github-release-token`.
   Keep the token out of Git, build parameters and shell command arguments.
   The initial token expires after 90 days; replace the secret before expiry.
3. Push the pipeline files to `main`. Run `bootstrap-releases.groovy` once in
   the administrator Script Console to create and start the monitor job.

For each new version, use GitHub **Releases → Draft a new release**, choose/create
its tag on the desired commit, then **Publish release**. No binary upload is
needed. Within approximately two minutes the monitor starts the builds; total
delivery time also depends on agent availability and build duration. The Mac
must be awake. A plain tag push or saved draft does not publish packages.

The monitor releases its Linux executor before waiting for the downstream build,
so one executor per agent is sufficient. The private controller needs outbound
HTTPS only. Ordinary `main` CI has no publication credential binding and continues
to archive packages in Jenkins. All release uploads use the explicit binding in
release stages, and credentials are not passed to application tests/builds.
