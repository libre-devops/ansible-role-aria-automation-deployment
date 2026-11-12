<div align="center">
  <a href="https://libredevops.org">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://libredevops.org/assets/libre-devops-white.png">
      <img alt="Libre DevOps" src="https://libredevops.org/assets/libre-devops-black.png" width="300">
    </picture>
  </a>
</div>

# Ansible Role: Aria Automation deployment

Requests, waits for, uses and deletes VMware Aria Automation 8 (vRealize Automation 8) deployments from a catalog item over the REST API, and adds their machines to the inventory. Built for short-lived test VMs. Nothing is needed on the control node beyond `ansible-core`.

[![CI](https://github.com/libre-devops/ansible-role-aria-automation-deployment/actions/workflows/ci.yml/badge.svg)](https://github.com/libre-devops/ansible-role-aria-automation-deployment/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/libre-devops/ansible-role-aria-automation-deployment?sort=semver&label=release)](https://github.com/libre-devops/ansible-role-aria-automation-deployment/releases/latest)
[![Galaxy](https://img.shields.io/badge/galaxy-libre__devops.aria__automation__deployment-EE0000?logo=ansible&logoColor=white)](https://galaxy.ansible.com/ui/standalone/roles/libre_devops/aria_automation_deployment/documentation/)
[![Licence](https://img.shields.io/github/license/libre-devops/ansible-role-aria-automation-deployment)](./LICENSE)

---

> **Status:** tested in CI against a mock of the Aria Automation API built from the vra-sdk-go client. Not yet run against a real Aria Automation: test with `just live` before relying on it.

## What it does

| State | What happens |
|---|---|
| `present` (default) | Signs in, then for each deployment in `aria_automation_deployment_deployments`: reuses the deployment with that name in the project if there is one, otherwise requests the catalog item. Waits for each to finish, stops with the request's error if one fails, then adds every machine to the in-memory inventory and, if you ask, writes them to a YAML inventory file. |
| `absent` | Deletes each deployment with that name in the project, if there is one, waits until it is gone, and removes the inventory file. |

It runs on the control node: put it in a play for `localhost`, or delegate it there. It uses `ansible.builtin.uri` only.

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Signing in](#signing-in)
- [Role variables](#role-variables)
- [How machines become hosts](#how-machines-become-hosts)
- [Provision now, fill in credentials, test later](#provision-now-fill-in-credentials-test-later)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [The API calls it makes](#the-api-calls-it-makes)
- [Developing](#developing)
- [Releasing](#releasing)
- [Sources](#sources)

## Requirements

| What | Detail |
|---|---|
| Control node | `ansible-core` 2.16 or later. No collections. |
| Aria Automation | VMware Aria Automation 8 or vRealize Automation 8, reachable over HTTPS from the control node. VMware Cloud Foundation Automation 9 signs in differently and is not supported. |
| Account | A user (or API token) that is a member of the project, with the catalog item shared with that project, and allowed to delete its own deployments for `absent`. |

## Installation

From Galaxy:

```bash
ansible-galaxy role install libre_devops.aria_automation_deployment
```

Or pin a release from GitHub, as in [`examples/requirements.yml`](./examples/requirements.yml):

```yaml
roles:
  - name: libre_devops.aria_automation_deployment
    src: https://github.com/libre-devops/ansible-role-aria-automation-deployment.git
    scm: git
    version: 1.0.0
```

Without Galaxy, or to keep a copy inside your organisation, see [Using the role without Galaxy](./docs/using-without-galaxy.md). It covers git, release archives, requirements files that point at your own servers, AWX and Automation Controller, and execution environments.

## Quick start

```yaml
- name: Build test VMs
  hosts: localhost
  gather_facts: false
  roles:
    - role: libre_devops.aria_automation_deployment
      vars:
        aria_automation_deployment_url: https://automation.example.com
        aria_automation_deployment_refresh_token: "{{ vault_aria_api_token }}"
        aria_automation_deployment_project: Test lab
        aria_automation_deployment_groups: [test_vms]
        aria_automation_deployment_deployments:
          - name: test-rhel9-01
            catalog_item: Linux server
            inputs:
              image: rhel9
              cpu: 2

- name: Use them
  hosts: test_vms
  tasks:
    - name: Check the operating system
      ansible.builtin.command: cat /etc/os-release
      changed_when: false
```

Run it again and nothing new is requested: `test-rhel9-01` already exists, so it is reused. Delete the VMs with the same variables and `aria_automation_deployment_state: absent`.

## Signing in

| Method | Variables | How it works |
|---|---|---|
| API token (preferred) | `aria_automation_deployment_refresh_token` | The role exchanges the token for an access token at `/iaas/api/login`. |
| User name and password | `aria_automation_deployment_username`, `aria_automation_deployment_password`, and `aria_automation_deployment_domain` for directory users | The role first exchanges them for a refresh token at `/csp/gateway/am/api/login`, the way VMware's own token script for the Terraform provider does. |

Keep the token or password in Ansible Vault or a secret store. The sign-in tasks use `no_log`, and the token and password are marked `no_log` in the argument specification. When sign-in fails, the role says which step failed and the HTTP status, without the response body.

API tokens expire. If the role says the refresh token was refused, create a new one.

## Role variables

Every variable except the two per-machine templates is validated against [`meta/argument_specs.yml`](./meta/argument_specs.yml) when the role starts. Defaults are in [`defaults/main.yml`](./defaults/main.yml).

### Connection and sign-in

| Variable | Default | Description |
|---|---|---|
| `aria_automation_deployment_url` | `""` | Base URL, such as `https://automation.example.com`. Required. |
| `aria_automation_deployment_validate_certs` | `true` | Check the server's TLS certificate. |
| `aria_automation_deployment_refresh_token` | `""` | API (refresh) token. Preferred. |
| `aria_automation_deployment_username` | `""` | User name, used when there is no token. |
| `aria_automation_deployment_password` | `""` | Its password. |
| `aria_automation_deployment_domain` | `""` | Identity domain, for directory (not local) users. |
| `aria_automation_deployment_http_timeout` | `60` | Seconds each API call may take. |

### Deployments

| Variable | Default | Description |
|---|---|---|
| `aria_automation_deployment_state` | `present` | `present` or `absent`. See [What it does](#what-it-does). |
| `aria_automation_deployment_deployments` | `[]` | The deployments, one item each. See the table below. |
| `aria_automation_deployment_project` | `""` | Project name or ID for items that do not set one. |
| `aria_automation_deployment_reason` | `Requested by Ansible` | Request reason for items that do not set one. |
| `aria_automation_deployment_timeout` | `3600` | Seconds to wait for a deployment to be created or deleted. |
| `aria_automation_deployment_poll_interval` | `30` | Seconds between status checks. |

Each item of `aria_automation_deployment_deployments`:

| Key | Default | Description |
|---|---|---|
| `name` | required | Deployment name. Unique in the project: the role uses it to find the deployment again. |
| `catalog_item` | required to create | Catalog item name or ID. Not needed for `absent`. |
| `catalog_item_version` | `""` | Catalog item version. Empty uses the current one. |
| `project` | `""` | Project name or ID. Empty uses `aria_automation_deployment_project`. |
| `inputs` | `{}` | The catalog item's inputs, exactly as the catalog item's form names them. |
| `reason` | `""` | Request reason. Empty uses `aria_automation_deployment_reason`. |

Names are looked up with the API's filters and then matched exactly, so `Linux server` never picks `Linux server (large)`. A name that matches more than one project or catalog item stops the role: use the ID.

### Hosts and the inventory file

| Variable | Default | Description |
|---|---|---|
| `aria_automation_deployment_machine_types` | `[Cloud.vSphere.Machine, Cloud.Machine]` | Resource types that become hosts. Networks, disks and the rest are left out. |
| `aria_automation_deployment_add_hosts` | `true` | Add each machine to the in-memory inventory, for later plays in the same run. |
| `aria_automation_deployment_groups` | `[aria_automation_machines]` | Inventory groups for the machines. |
| `aria_automation_deployment_host_name` | `{{ resource.properties.resourceName \| default(resource.name) }}` | Inventory host name of each machine. A template, see [How machines become hosts](#how-machines-become-hosts). |
| `aria_automation_deployment_host_vars` | `{ansible_host: <address>}` | Host variables of each machine. Each value is a template. The default sets `ansible_host` from `resource.properties.address`, or the host name when there is no address. |
| `aria_automation_deployment_inventory_file` | `""` | Path on the control node to write the machines to as a YAML inventory. Empty writes nothing. `absent` removes it. |
| `aria_automation_deployment_inventory_exclude_vars` | `(?i)(pass\|secret\|token)` | Host variables whose names match this are never written to the inventory file. |
| `aria_automation_deployment_wait_for_connection` | `false` | Wait until Ansible can connect to each machine. Needs credentials for them in this run. |
| `aria_automation_deployment_connection_timeout` | `600` | Seconds to wait for each machine. |
| `aria_automation_deployment_no_log` | `true` | Hide deployment details from Ansible's output, because resource properties can hold secrets. Set `false` to see them while debugging. |

`aria_automation_deployment_host_name` and `aria_automation_deployment_host_vars` are not in the argument specification on purpose. They are templates for each machine, and Ansible's specification check templates every value before the role runs, when no machine exists yet. The role checks their types itself, once per machine.

### Facts set by the role

`aria_automation_deployment_results` lists every deployment of a `present` run:

```yaml
- name: test-rhel9-01
  id: 6f1c2a0e-...           # deployment ID
  project_id: 1b7e9d42-...
  status: CREATE_SUCCESSFUL
  requested: true            # false when an existing deployment was reused
  machines:
    - name: Cloud_vSphere_Machine_1
      id: 9a3f...
      type: Cloud.vSphere.Machine
      deployment: test-rhel9-01
      address: 192.0.2.21    # resource.properties.address, or empty
      properties: {...}      # every property of the machine resource
```

## How machines become hosts

Each machine in each deployment becomes one inventory host. The role templates `aria_automation_deployment_host_name` and every value of `aria_automation_deployment_host_vars` once per machine, with the machine as `resource`:

| In templates | What it is |
|---|---|
| `resource.name` | The resource's name in the deployment, such as `Cloud_vSphere_Machine_1` |
| `resource.type` | Its type, such as `Cloud.vSphere.Machine` |
| `resource.properties` | Every property of the machine, including custom properties your catalog item or blueprint sets |
| `resource.deployment` | The deployment name |

So whatever your catalog item puts on its machines can become a host name or a host variable. For example, a catalog item that sets a fully qualified name in a custom property called `fqdn`, and that should be reached through it:

```yaml
aria_automation_deployment_host_name: "{{ resource.properties.fqdn }}"
aria_automation_deployment_host_vars:
  ansible_host: "{{ resource.properties.fqdn }}"
  ansible_user: cloud-user
  build_image: "{{ resource.properties.image | default('unknown') }}"
```

To see what properties your machines have, run once with `aria_automation_deployment_no_log: false` and look at `aria_automation_deployment_results`, or open the deployment in Aria Automation.

The hosts are added through a small action plugin in the role, `aria_automation_deployment_add_host`, which hands a dictionary of variables to `ansible.builtin.add_host`. Passing that dictionary to `add_host` directly would mean templating the whole task's arguments, which Ansible warns is unsafe with data that comes from an API.

## Provision now, fill in credentials, test later

Often the VMs cannot be used in the same run: their credentials only exist once they are built, or someone has to put a key on them first. For that, write the machines to an inventory file and come back later:

1. **Provision**, writing the inventory file:

   ```yaml
   aria_automation_deployment_groups: [test_vms]
   aria_automation_deployment_inventory_file: inventory/test-vms.yml
   ```

   The role writes something like this, and rewrites it on every run:

   ```yaml
   all:
     children:
       test_vms:
         hosts:
           test-rhel8-01:
             ansible_host: 192.0.2.31
             ansible_user: root
           test-rhel9-01:
             ansible_host: 192.0.2.21
             ansible_user: root
   ```

   Host variables named like a password, secret or token (`ansible_password`, `ansible_become_pass` and so on) are never written to the file, even when `aria_automation_deployment_host_vars` sets them.

2. **Fill in credentials** next to the file, not in it, encrypted:

   ```bash
   mkdir -p inventory/group_vars/test_vms
   ansible-vault create inventory/group_vars/test_vms/vault.yml   # ansible_password: ...
   ```

3. **Bootstrap SSH access**, for example with [`libre_devops.ssh_bootstrap`](https://github.com/libre-devops/ansible-role-ssh-bootstrap) to put your key on the VMs:

   ```bash
   ansible-playbook -i inventory/test-vms.yml ssh-bootstrap.yml --ask-vault-pass
   ```

4. **Test**, with the same inventory: `ansible-playbook -i inventory/test-vms.yml tests.yml`.

5. **Delete** the VMs with the same variables and `aria_automation_deployment_state: absent`. That also removes `inventory/test-vms.yml`, and leaves `group_vars` alone.

## Examples

### Two VMs from different catalog items and projects

```yaml
aria_automation_deployment_deployments:
  - name: test-rhel9-01
    catalog_item: Linux server
    project: Test lab
    inputs: {image: rhel9}
  - name: test-win2022-01
    catalog_item: 6a1b9f7c-2d4e-4c3b-9a8f-0e1d2c3b4a59   # ID, when names are ambiguous
    catalog_item_version: "3"
    project: 8d2f4a6b-1c3e-4f5a-9b7d-2e4f6a8c0b1d
    inputs: {cpu: 4, memory_mb: 4096}
```

### Build, wait for SSH, use, delete

```yaml
- name: Build
  hosts: localhost
  gather_facts: false
  roles:
    - role: libre_devops.aria_automation_deployment
      vars:
        aria_automation_deployment_wait_for_connection: true
        aria_automation_deployment_host_vars:
          ansible_host: "{{ resource.properties.address }}"
          ansible_user: cloud-user
          ansible_ssh_private_key_file: ~/.ssh/test-vms

- name: Test
  hosts: aria_automation_machines
  tasks:
    - name: Run the tests
      ansible.builtin.include_tasks: tests.yml

- name: Delete
  hosts: localhost
  gather_facts: false
  roles:
    - role: libre_devops.aria_automation_deployment
      vars:
        aria_automation_deployment_state: absent
```

Put the deployment list and sign-in in `group_vars` or a vars file, so the build and delete plays share them.

### Leave the in-memory inventory alone

```yaml
aria_automation_deployment_add_hosts: false
aria_automation_deployment_inventory_file: inventory/test-vms.yml
```

## Troubleshooting

| Symptom | What to check |
|---|---|
| `Signing in ... failed (HTTP 401)` | User name, password or `aria_automation_deployment_domain`. Directory users usually need the domain. |
| `... refused the refresh token` | The API token has expired or was revoked, or the URL points at the wrong appliance. |
| `Project '...' matched 0 projects` | The name is wrong, or the account is not a member. Names are matched exactly, including case. |
| `Catalog item '...' matched 0 items` | The catalog item is not shared with that project, or the name differs. |
| `... is CREATE_FAILED: ...` | The message has the last request's details from Aria Automation. Delete the deployment (`absent`) before requesting it again, because the role reuses a deployment with the same name. |
| A new run did not pick up changed inputs | The deployment already exists, so it is reused as it is. The role does not update deployments: delete and recreate it. |
| No hosts were added | The machines' resource type is not in `aria_automation_deployment_machine_types`. Look at `aria_automation_deployment_results` with `aria_automation_deployment_no_log: false`. |
| `ansible_host` is empty or wrong | The address is in a different property. Set `aria_automation_deployment_host_vars` to read the right one. |
| Timed out waiting | Raise `aria_automation_deployment_timeout`. The deployment carries on in Aria Automation either way. |

## The API calls it makes

| Call | Used for | Confirmed from |
|---|---|---|
| `POST /csp/gateway/am/api/login?access_token` with `username`, `password`, `domain` | User name and password to refresh token | VMware's token guide and script in the [terraform-provider-vra](https://github.com/vmware/terraform-provider-vra/blob/main/docs/refresh_token_vra.md) repository |
| `POST /iaas/api/login` with `refreshToken` | Refresh token to bearer token | [vra-sdk-go](https://github.com/vmware/vra-sdk-go) `login` client, and the Terraform provider's `client.go` |
| `GET /iaas/api/projects?$filter=name eq '...'` | Project by name | vra-sdk-go `project` client (`getProjects`, `$filter`) |
| `GET /catalog/api/items?search=...&projects=...` | Catalog item by name | vra-sdk-go `catalog_items` client (`search`, `projects`) |
| `POST /catalog/api/items/{id}/request` with `deploymentName`, `projectId`, `version`, `inputs`, `reason` | Request a deployment; returns `deploymentId` | vra-sdk-go `CatalogItemRequest` and `CatalogItemRequestResponse` models |
| `GET /deployment/api/deployments?name=...&projects=...` | Existing deployment by name | vra-sdk-go `deployments` client (`name`, `projects`) |
| `GET /deployment/api/deployments/{id}?expand=resources&expand=lastRequest` | Status, resources and the last request's details | vra-sdk-go `getDeploymentByIdV3` and the `Deployment` model's statuses |
| `DELETE /deployment/api/deployments/{id}` | Delete, then wait for 404 | vra-sdk-go `deleteDeploymentUsingDELETE_2`, and the Terraform provider waiting for 404 |

Not confirmed, and handled defensively:

- Whether the `search` and `name` filters match whole names or parts of them. The role matches the results exactly itself.
- Whether the deployment list includes deleted deployments. The role ignores any with status `DELETE_SUCCESSFUL`.
- The role has been tested against the mock in this repository, built from the shapes above, not yet against a live Aria Automation. Please report differences you find.

## Developing

You need [uv](https://docs.astral.sh/uv/) and [just](https://github.com/casey/just). CI runs the same recipes. No containers are needed.

| Recipe | What it does |
|---|---|
| `just deps` | Installs the pinned Python tools (`uv.lock`). |
| `just lint` | `yamllint`, `ansible-lint` on the production profile, `zizmor` on the workflows, and `ruff` on the Python. |
| `just test` | Runs the Molecule scenario against the mock API. |
| `just mock [port]` | Starts the mock API in the foreground, for trying the role by hand. |
| `just live [args]` | Runs [`examples/playbook.yml`](./examples/playbook.yml) against a real Aria Automation, with your vars file: `just live -e @lab.vault.yml --ask-vault-pass`. |
| `just secrets` | Scans the git history with gitleaks. |

[`molecule/fixtures/mock_aria.py`](./molecule/fixtures/mock_aria.py) is a stand-in for the API, using only the Python standard library. It serves the calls above with the same request and response shapes and keeps everything in memory. A new deployment is in progress for two polls before it succeeds with one machine and one network, the `Broken server` catalog item fails with a message, and a deleted deployment answers 404 after one more poll.

The `default` scenario runs on the control node:

| Step | What it proves |
|---|---|
| converge | Two deployments, one by names and one by IDs, are created and waited for. Their machines are in the in-memory groups with the templated host variables, and the inventory file lists them without the password. |
| idempotence | A second run reuses both deployments and requests nothing. |
| side_effect | A failed deployment stops the role with the request's error. Then `absent`, signed in with a user name and password, deletes everything, including a name that never existed, without error. |
| verify | The mock saw three catalog requests, three deletes and one password sign-in, nothing is left, and the inventory file is gone. |
| destroy | Stops the mock. It also runs first, to clear a mock left by a failed run. |

## Releasing

1. Move the Unreleased entries in [`CHANGELOG.md`](./CHANGELOG.md) under the new version.
2. Run `just release 1.2.3`. It tags the commit and pushes the tag.
3. The Release workflow creates the GitHub release, imports the tag into Galaxy, which takes the version from the tag, and installs it back from Galaxy to check. It needs the `GALAXY_API_KEY` secret, which the libre-devops organisation provides. The import goes through Galaxy's API with [`scripts/galaxy-import.py`](./scripts/galaxy-import.py), not `ansible-galaxy role import`, because Galaxy namespaces cannot contain a hyphen: the role namespace is `libre_devops` and the GitHub organisation is `libre-devops`, which that command cannot handle. If the import fails, fix the cause and run the Release workflow by hand with the tag to import it again.

## Sources

Retrieved 9 November 2026.

| Topic | Source |
|---|---|
| API paths, parameters and models | [vmware/vra-sdk-go](https://github.com/vmware/vra-sdk-go), `pkg/client` and `pkg/models` |
| Sign-in and the deployment life cycle | [vmware/terraform-provider-vra](https://github.com/vmware/terraform-provider-vra), `vra/client.go` and `vra/resource_deployment.go` |
| User name and password to refresh token | [terraform-provider-vra: Get your refresh token](https://github.com/vmware/terraform-provider-vra/blob/main/docs/refresh_token_vra.md) |
| Catalog item request body | [Broadcom developer portal: CatalogItemRequest](https://developer.broadcom.com/xapis/vrealize-automation-catalog-api/latest/data-structures/CatalogItemRequest/) |

## Licence

[MIT](./LICENSE).
