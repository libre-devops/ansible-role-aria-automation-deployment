#!/usr/bin/env python3
"""A stand-in for the VMware Aria Automation 8 API, for the Molecule tests.

It serves only the calls the role makes, with the request and response shapes of the
vra-sdk-go client (https://github.com/vmware/vra-sdk-go), and keeps everything in memory:

  POST   /csp/gateway/am/api/login?access_token   user name and password -> refresh_token
  POST   /iaas/api/login                          refreshToken -> bearer token
  GET    /iaas/api/projects?$filter=name eq 'X'   projects
  GET    /catalog/api/items?search=X&projects=Y   catalog items
  POST   /catalog/api/items/{id}/request          new deployment -> [{deploymentId, ...}]
  GET    /deployment/api/deployments?name=X       deployments
  GET    /deployment/api/deployments/{id}         one deployment, with resources
  DELETE /deployment/api/deployments/{id}         delete it

A new deployment reports CREATE_INPROGRESS for two polls, then CREATE_SUCCESSFUL with one
machine and one network. The "Broken server" catalog item ends CREATE_FAILED. A deleted
deployment reports DELETE_INPROGRESS once, then 404. Test helpers:

  GET    /mock/stats      counts of logins, catalog requests and deletes, and live deployments
  POST   /mock/shutdown   stop the server

Usage: mock_aria.py [--port 18943]
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Made-up credentials the tests sign in with. Nothing real.
USERNAME = "molecule"
PASSWORD = "molecule-password"  # noqa: S105
REFRESH_TOKEN = "molecule-refresh-token"  # noqa: S105
BEARER = "molecule-bearer-token"

PROJECTS = [
    {"id": "11111111-1111-4111-8111-111111111111", "name": "Test lab"},
    {"id": "22222222-2222-4222-8222-222222222222", "name": "Test lab archive"},
]
CATALOG_ITEMS = [
    {"id": "33333333-3333-4333-8333-333333333333", "name": "Linux server", "projectIds": [PROJECTS[0]["id"]]},
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "name": "Linux server (large)",
        "projectIds": [PROJECTS[0]["id"]],
    },
    {
        "id": "55555555-5555-4555-8555-555555555555",
        "name": "Broken server",
        "projectIds": [PROJECTS[0]["id"]],
    },
]
POLLS_IN_PROGRESS = 2

LOCK = threading.Lock()
DEPLOYMENTS: dict[str, dict] = {}
STATS = {"csp_logins": 0, "iaas_logins": 0, "catalog_requests": 0, "deletes": 0}


def _machine(deployment: dict, number: int) -> dict:
    name = f"{deployment['name']}-{number:02d}"
    return {
        "id": str(uuid.uuid4()),
        "name": f"Cloud_vSphere_Machine_{number}",
        "type": "Cloud.vSphere.Machine",
        "properties": {
            "resourceName": name,
            "address": f"192.0.2.{10 + len(DEPLOYMENTS) * 10 + number}",
            "osType": "LINUX",
            "cpuCount": deployment["inputs"].get("cpu", 2),
            # A made-up secret, to prove the role never writes secrets to the inventory file.
            "mockRootSecret": "not-a-real-secret",
        },
    }


def _deployment_view(deployment: dict) -> dict:
    """Advance the deployment's state by one poll and return what the API would."""
    if deployment["status"] == "CREATE_INPROGRESS":
        deployment["polls"] += 1
        if deployment["polls"] > POLLS_IN_PROGRESS:
            if deployment["catalogItemId"] == CATALOG_ITEMS[2]["id"]:
                deployment["status"] = "CREATE_FAILED"
                deployment["lastRequest"] = {
                    "status": "FAILED",
                    "details": "Mock failure: no capacity in the placement zone",
                }
            else:
                deployment["status"] = "CREATE_SUCCESSFUL"
                deployment["lastRequest"] = {"status": "SUCCESSFUL", "details": ""}
                deployment["resources"] = [
                    _machine(deployment, 1),
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Cloud_Network_1",
                        "type": "Cloud.Network",
                        "properties": {},
                    },
                ]
    view = {k: v for k, v in deployment.items() if k != "polls"}
    return view


class Handler(BaseHTTPRequestHandler):
    server_version = "MockAriaAutomation/1.0"

    def log_message(self, fmt, *args):  # Keep the Molecule output readable.
        return

    def _send(self, status: int, body=None) -> None:
        data = json.dumps(body if body is not None else {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _authorised(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {BEARER}":
            return True
        self._send(401, {"message": "Unauthorized"})
        return False

    def do_POST(self):  # noqa: N802 (http.server naming)
        url = urlparse(self.path)
        with LOCK:
            if url.path == "/csp/gateway/am/api/login":
                body = self._body()
                STATS["csp_logins"] += 1
                if body.get("username") == USERNAME and body.get("password") == PASSWORD:
                    return self._send(200, {"refresh_token": REFRESH_TOKEN})
                return self._send(401, {"message": "Invalid credentials"})
            if url.path == "/iaas/api/login":
                STATS["iaas_logins"] += 1
                if self._body().get("refreshToken") == REFRESH_TOKEN:
                    return self._send(200, {"token": BEARER, "tokenType": "Bearer"})
                return self._send(400, {"message": "Invalid refresh token"})
            if url.path == "/mock/shutdown":
                self._send(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
            if not self._authorised():
                return None
            match = re.fullmatch(r"/catalog/api/items/([^/]+)/request", url.path)
            if match:
                item = next((i for i in CATALOG_ITEMS if i["id"] == match.group(1)), None)
                if item is None:
                    return self._send(404, {"message": "Catalog item not found"})
                body = self._body()
                if body.get("projectId") not in item["projectIds"]:
                    return self._send(400, {"message": "Catalog item not shared with the project"})
                STATS["catalog_requests"] += 1
                deployment_id = str(uuid.uuid4())
                DEPLOYMENTS[deployment_id] = {
                    "id": deployment_id,
                    "name": body["deploymentName"],
                    "projectId": body["projectId"],
                    "catalogItemId": item["id"],
                    "inputs": body.get("inputs", {}),
                    "status": "CREATE_INPROGRESS",
                    "resources": [],
                    "lastRequest": {"status": "INPROGRESS", "details": ""},
                    "polls": 0,
                }
                return self._send(
                    201, [{"deploymentId": deployment_id, "deploymentName": body["deploymentName"]}]
                )
            return self._send(404, {"message": "Not found"})

    def do_GET(self):  # noqa: N802 (http.server naming)
        url = urlparse(self.path)
        query = parse_qs(url.query)
        with LOCK:
            if url.path == "/mock/stats":
                live = sorted(d["name"] for d in DEPLOYMENTS.values())
                return self._send(200, {**STATS, "deployments": live})
            if not self._authorised():
                return None
            if url.path == "/iaas/api/projects":
                match = re.fullmatch(r"name eq '(.*)'", query.get("$filter", [""])[0])
                content = [p for p in PROJECTS if match and p["name"] == match.group(1)]
                return self._send(200, {"content": content, "totalElements": len(content)})
            if url.path == "/catalog/api/items":
                search = query.get("search", [""])[0].lower()
                projects = query.get("projects", [None])[0]
                content = [
                    {"id": i["id"], "name": i["name"]}
                    for i in CATALOG_ITEMS
                    if search in i["name"].lower() and (projects is None or projects in i["projectIds"])
                ]
                return self._send(200, {"content": content, "totalElements": len(content)})
            if url.path == "/deployment/api/deployments":
                name = query.get("name", [""])[0].lower()
                projects = query.get("projects", [None])[0]
                content = [
                    {k: v for k, v in d.items() if k not in ("polls", "resources")}
                    for d in DEPLOYMENTS.values()
                    if name in d["name"].lower() and (projects is None or d["projectId"] == projects)
                ]
                return self._send(200, {"content": content, "totalElements": len(content)})
            match = re.fullmatch(r"/deployment/api/deployments/([^/]+)", url.path)
            if match:
                deployment = DEPLOYMENTS.get(match.group(1))
                if deployment is None:
                    return self._send(404, {"message": "Deployment not found"})
                if deployment["status"] == "DELETE_INPROGRESS":
                    del DEPLOYMENTS[deployment["id"]]
                    return self._send(200, {k: v for k, v in deployment.items() if k != "polls"})
                return self._send(200, _deployment_view(deployment))
            return self._send(404, {"message": "Not found"})

    def do_DELETE(self):  # noqa: N802 (http.server naming)
        url = urlparse(self.path)
        with LOCK:
            if not self._authorised():
                return None
            match = re.fullmatch(r"/deployment/api/deployments/([^/]+)", url.path)
            deployment = DEPLOYMENTS.get(match.group(1)) if match else None
            if deployment is None:
                return self._send(404, {"message": "Deployment not found"})
            STATS["deletes"] += 1
            deployment["status"] = "DELETE_INPROGRESS"
            return self._send(200, {"id": str(uuid.uuid4()), "name": "Delete", "status": "INPROGRESS"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=18943)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
