#!/usr/bin/env python3
"""Phase 6 — register SuburbScout image as a Foundry Hosted Agent version.

Prereqs:
  - az login (or managed identity)
  - Foundry Project Manager on the project
  - Image already in ACR (phase5_push_acr.sh)
  - Project managed identity has AcrPull on the registry

Usage:
  export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
  # Hosted Agents require a supported region (e.g. eastus2, not eastus):
  # https://suburbscout-project-eastus2.services.ai.azure.com/api/projects/suburbscout-hosted
  export AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-chat-deployment>"
  export DATABASE_URL="<supabase-connection-string>"   # optional but recommended

  python scripts/phase6_deploy_foundry.py \\
    --image suburbscoutacr.azurecr.io/suburbscout-hosted:v1 \\
    --agent-name suburbscout-hosted

  python scripts/phase6_deploy_foundry.py --image ... --invoke "What is the commute from Maynard?"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _build_hosted_agent_definition(
    *,
    cpu: str,
    memory: str,
    image: str,
    environment_variables: dict[str, str],
    protocol_versions: list,
    use_container_configuration: bool = False,
):
    """Build HostedAgentDefinition for image-based hosted agents.

    SDK 2.1+ uses HostedAgentDefinition (not ImageBasedHostedAgentDefinition — that class
    does not exist in Python). Prefer container_configuration on newer API paths; legacy
    top-level image field still works for many deployments.
    """
    from azure.ai.projects.models import ContainerConfiguration, HostedAgentDefinition

    base: dict = {
        "cpu": cpu,
        "memory": memory,
        "environment_variables": environment_variables,
    }
    if use_container_configuration:
        base["container_configuration"] = ContainerConfiguration(image=image)
    else:
        base["image"] = image

    # API rules (azure-ai-projects 2.1+):
    # - legacy top-level image → container_protocol_versions
    # - container_configuration → protocol_versions only
    protocol_kw = "protocol_versions" if use_container_configuration else "container_protocol_versions"
    fallback_kw = "protocol_versions"

    for kw in (protocol_kw, fallback_kw):
        try:
            definition = HostedAgentDefinition(**base, **{kw: protocol_versions})
        except TypeError:
            continue

        # Legacy SDK __init__ may only accept protocol_versions; patch for image field API.
        if (
            not use_container_configuration
            and kw == fallback_kw
            and "container_protocol_versions" in getattr(HostedAgentDefinition, "__annotations__", {})
        ):
            definition.container_protocol_versions = protocol_versions
            definition.protocol_versions = None

        return definition

    raise RuntimeError(
        "HostedAgentDefinition does not accept container_protocol_versions or "
        "protocol_versions in this azure-ai-projects version"
    )


def _poll_active(project, agent_name: str, version: str, *, timeout_s: int = 300) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        info = project.agents.get_version(agent_name=agent_name, agent_version=version)
        status = getattr(info, "status", None) or info.get("status")
        print(f"  status: {status}")
        if status == "active":
            return info if isinstance(info, dict) else info.as_dict()
        if status == "failed":
            err = getattr(info, "error", None) or info.get("error")
            _fail(f"agent version failed: {err}")
        time.sleep(5)
    _fail(f"timed out waiting for active (>{timeout_s}s)")


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(SERVICE_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Deploy Foundry Hosted Agent from ACR image")
    parser.add_argument("--image", required=True, help="Full ACR image URL with tag")
    parser.add_argument("--agent-name", default="suburbscout-hosted")
    parser.add_argument("--cpu", default="1")
    parser.add_argument("--memory", default="2Gi")
    parser.add_argument("--invoke", default="", help="Optional test prompt after deploy")
    parser.add_argument("--no-poll", action="store_true")
    parser.add_argument(
        "--legacy-image-field",
        action="store_true",
        help="Use top-level image + container_protocol_versions (older API shape)",
    )
    args = parser.parse_args()

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    if not endpoint:
        _fail("FOUNDRY_PROJECT_ENDPOINT is not set")

    model = (
        os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        or ""
    ).strip()
    if not model:
        _fail("Set AZURE_AI_MODEL_DEPLOYMENT_NAME or AZURE_OPENAI_DEPLOYMENT_NAME")

    try:
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import AgentProtocol, ProtocolVersionRecord
        from azure.identity import DefaultAzureCredential

        from app.hosted_env import build_phase6_container_env_vars
    except ImportError as exc:
        _fail(f"pip install 'azure-ai-projects>=2.1.0' — {exc}")

    env_vars = build_phase6_container_env_vars()
    if not env_vars.get("AZURE_AI_MODEL_DEPLOYMENT_NAME"):
        _fail("Set AZURE_AI_MODEL_DEPLOYMENT_NAME or AZURE_OPENAI_DEPLOYMENT_NAME")

    print(f"=== Phase 6: create hosted agent version ===")
    print(f"  endpoint: {endpoint}")
    print(f"  agent:    {args.agent_name}")
    print(f"  image:    {args.image}")
    print(f"  model:    {model}")
    print(f"  container env keys: {sorted(env_vars.keys())}")

    protocol_versions = [
        ProtocolVersionRecord(protocol=AgentProtocol.RESPONSES, version="1.0.0")
    ]

    definition = _build_hosted_agent_definition(
        cpu=args.cpu,
        memory=args.memory,
        image=args.image,
        environment_variables=env_vars,
        protocol_versions=protocol_versions,
        use_container_configuration=not args.legacy_image_field,
    )
    payload_keys = list(definition.as_dict().keys())
    print(f"  definition payload keys: {payload_keys}")

    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True)

    version = project.agents.create_version(
        agent_name=args.agent_name,
        definition=definition,
    )

    ver = getattr(version, "version", None) or version.get("version")
    print(f"  created version: {ver}")

    if not args.no_poll:
        print("Polling until active...")
        _poll_active(project, args.agent_name, str(ver))

    playground = (
        f"{endpoint.rsplit('/api/projects/', 1)[0]}/build/agents/{args.agent_name}/build?version={ver}"
        if "/api/projects/" in endpoint
        else "(see Foundry portal → Build → Agents)"
    )
    print(f"\nAgent endpoint pattern:")
    print(f"  {endpoint.rsplit('/api/projects/', 1)[0]}/api/projects/<project>/agents/{args.agent_name}/versions/{ver}")
    print(f"Playground: {playground}")

    if args.invoke:
        print(f"\n=== Invoke test: {args.invoke!r} ===")
        openai_client = project.get_openai_client()
        response = openai_client.responses.create(
            input=args.invoke,
            extra_body={"agent": {"name": args.agent_name, "type": "agent_reference"}},
        )
        text = getattr(response, "output_text", None) or str(response)
        print(text[:2000])

    print("\n=== Phase 6 deploy: DONE ===")
    print("Screenshot: portal agent status + invoke output. Tear down when finished to limit cost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
