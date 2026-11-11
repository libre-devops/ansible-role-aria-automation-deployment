# Changelog

Notable changes to this role. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Fixed

- Galaxy import: call Galaxy's import API with the `libre_devops` namespace and the GitHub clone URL, because `ansible-galaxy role import` sends the GitHub organisation name, which Galaxy refuses with HTTP 500. The import now waits for the result and prints Galaxy's log, and the Release workflow can be run by hand to import a tag again.

## 1.0.0 - 2026-11-11

### Added

- First release.
- Sign-in with an API (refresh) token, or a user name, password and identity domain.
- Deployments requested from catalog items by name or ID, in projects by name or ID, with inputs, version and reason, and reused when one with the same name already exists in the project.
- Waiting for each deployment, and stopping with the last request's details when it fails.
- Machines added to the in-memory inventory with templated host names and host variables, through a role-local `add_host` wrapper that takes the variables as one dictionary.
- An optional YAML inventory file of the machines, without passwords, secrets or tokens, for provisioning now and testing in a later run.
- `absent` deletes the deployments and waits until they are gone.
- The `aria_automation_deployment_results` fact.
- A Molecule scenario against a mock of the Aria Automation API.
