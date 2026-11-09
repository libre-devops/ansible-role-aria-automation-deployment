# Security policy

## Reporting a vulnerability

Report vulnerabilities in this role privately, through [GitHub's private vulnerability reporting](https://github.com/libre-devops/ansible-role-aria-automation-deployment/security/advisories/new). Do not open a public issue.

## What the role handles that is sensitive

- **Credentials.** The API token, or the user name and password, are only sent to Aria Automation's sign-in endpoints. The tasks that send them, and the access token they return, use `no_log`, and the token and password are marked `no_log` in the argument specification. Keep them in Ansible Vault or a secret store.
- **Resource properties.** Catalog items can put secrets in a machine's custom properties. Deployment details are hidden from Ansible's output unless you set `aria_automation_deployment_no_log: false`.
- **The inventory file.** Host variables whose names match `aria_automation_deployment_inventory_exclude_vars` (by default anything with `pass`, `secret` or `token` in the name) are never written to it. Credentials for the machines belong in Ansible Vault, in `group_vars` or `host_vars` next to the file.
- **Templated host variables.** The role passes host variables to `add_host` as one argument through its own small action plugin, rather than templating the whole task's arguments, which Ansible warns is unsafe with data from an API.
