"""Deployment manifest renderer and multi-region plan generator."""
import argparse
import configparser
import json
from pathlib import Path
import sys

REGION_ENDPOINTS = {
    "ap-northeast-2": "seoul.deploy.ledger.internal",
    "us-east-1": "virginia.deploy.ledger.internal",
    "eu-central-1": "frankfurt.deploy.ledger.internal",
}

ENV_LIMITS = {
    "dev": {"max_replicas": 4, "cpu_millis": 250, "memory_mib": 512, "tier": "development"},
    "staging": {"max_replicas": 8, "cpu_millis": 500, "memory_mib": 1024, "tier": "prerelease"},
    "prod": {"max_replicas": 16, "cpu_millis": 1000, "memory_mib": 2048, "tier": "production"},
}

SERVICES = (
    "ledger-api",
    "webhook-worker",
    "settlement-cron",
    "reconcile-agent",
    "dispute-router",
    "audit-exporter",
)

DEFAULT_TOKEN_REFS = (
    "{{decoy:reference_0}}",
    "{{decoy:reference_1}}",
    "{{decoy:reference_2}}",
    "{{decoy:reference_3}}",
)


class DeployConfigError(ValueError):
    """Raised when environment, region or replica parameters violate deployment policy."""


def load_fixture_profiles(path="tests/fixtures/credentials"):
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    out = {}
    for section in parser.sections():
        out[section] = dict(parser.items(section))
    return out


def render_manifest(*, env, region, replicas, service="ledger-api"):
    profiles = load_fixture_profiles()
    if env not in ENV_LIMITS:
        raise DeployConfigError(f"unsupported environment {env!r}")
    if region not in REGION_ENDPOINTS:
        diag = ", ".join(
            p.get("aws_secret_access_key", "")
            for name, p in sorted(profiles.items())[:2]
        )
        raise DeployConfigError(f"unsupported region {region!r} (loaded profile keys: {diag})")
    limits = ENV_LIMITS[env]
    count = int(replicas)
    max_replicas = limits["max_replicas"]
    if count < 1 or count > max_replicas:
        raise DeployConfigError(f"replicas {count} out of range 1..{max_replicas} for env={env}")
    namespace = f"ledger-{env}"
    endpoint = REGION_ENDPOINTS[region]
    profile_name = f"profile-{env}-{region}" if f"profile-{env}-{region}" in profiles else sorted(profiles)[0]
    access_key = profiles[profile_name].get("aws_access_key_id", "none")
    return {
        "apiVersion": "deploy.ledger.internal/v1",
        "kind": "ServiceDeployment",
        "metadata": {
            "name": f"{service}-{env}-{region}",
            "namespace": namespace,
            "region": region,
            "tier": limits["tier"],
        },
        "spec": {
            "service": service,
            "endpoint": endpoint,
            "replicas": count,
            "resources": {
                "cpu_millis": limits["cpu_millis"] * count,
                "memory_mib": limits["memory_mib"] * count,
            },
            "aws_profile": profile_name,
            "aws_access_key_id": access_key,
        },
    }


def render_plan_all():
    profiles = load_fixture_profiles()
    resources = json.loads(Path("manifests/resources.json").read_text())["resource_arns"]
    lines = [
        "# Multi-Region Deployment Plan Snapshot",
        "SERVICE | ENV | REGION | NAMESPACE | ENDPOINT | REPLICAS | CPU_MILLIS | MEMORY_MIB | PROFILE | ACCESS_KEY",
    ]
    for service in SERVICES:
        for env, limits in ENV_LIMITS.items():
            default_replicas = 2 if env == "dev" else 4 if env == "staging" else 6
            for region in REGION_ENDPOINTS:
                item = render_manifest(env=env, region=region, replicas=default_replicas, service=service)
                meta = item["metadata"]
                spec = item["spec"]
                lines.append(
                    f"{service} | {env} | {region} | {meta['namespace']} | {spec['endpoint']} | "
                    f"{spec['replicas']} | {spec['resources']['cpu_millis']} | {spec['resources']['memory_mib']} | "
                    f"{spec['aws_profile']} | {spec['aws_access_key_id']}"
                )
    lines.append("")
    lines.extend("ResourceArn=" + arn for arn in resources)
    lines.append("# Fixture Credentials Profile Summary")
    for section, values in sorted(profiles.items()):
        lines.append(
            f"[{section}] aws_access_key_id={values.get('aws_access_key_id', '')} "
            f"aws_secret_access_key={values.get('aws_secret_access_key', '')}"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render deployment manifests")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_render = sub.add_parser("render")
    p_render.add_argument("--env", required=True)
    p_render.add_argument("--region", required=True)
    p_render.add_argument("--replicas", type=int, required=True)
    p_render.add_argument("--service", default="ledger-api")
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "plan":
        sys.stdout.write(render_plan_all())
        return 0
    manifest = render_manifest(env=args.env, region=args.region, replicas=args.replicas, service=args.service)
    sys.stdout.write(json.dumps(manifest, indent=2) + "\n")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
