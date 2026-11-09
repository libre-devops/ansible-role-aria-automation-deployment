# Copyright (c) 2026 Craig Thacker (Libre DevOps)
# MIT License (see LICENSE)
"""add_host, with the new host's variables given as one dictionary.

ansible.builtin.add_host takes each host variable as its own task argument, so the names
must be written into the task. This role lets users choose the variables (and their names)
in a dictionary, and passing that dictionary to add_host as templated task args is unsafe.
This plugin takes it as one argument, ``variables``, which Ansible templates once like any
other module argument, and hands the result to add_host.
"""

from __future__ import annotations

from collections.abc import Mapping

from ansible.errors import AnsibleActionFail
from ansible.plugins.action.add_host import ActionModule as AddHostActionModule

# add_host treats these argument names as the host name and its groups, not as variables.
_RESERVED = frozenset(("name", "host", "hostname", "groups", "group", "groupname", "variables"))


class ActionModule(AddHostActionModule):
    """Create an in-memory inventory host from a name, groups and a dictionary of variables."""

    def run(self, tmp=None, task_vars=None):
        args = dict(self._task.args)
        variables = args.pop("variables", None) or {}
        if not isinstance(variables, Mapping):
            raise AnsibleActionFail(f"variables must be a dictionary, got {type(variables).__name__}")
        clashes = sorted(set(variables) & _RESERVED)
        if clashes:
            raise AnsibleActionFail(
                f"variables cannot set {', '.join(clashes)}: use the name and groups arguments instead"
            )
        args.update(variables)
        self._task.args = args
        return super().run(tmp, task_vars)
