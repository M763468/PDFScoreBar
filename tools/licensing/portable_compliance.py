#!/usr/bin/env python3
"""Rights/notice/source gate for a built Windows portable folder (#553).

The Windows portable ships a private CPython, third-party wheels with native DLLs,
model weights and fonts. ``runtime/build_manifest.json`` (#535/#551) inventories every
shipped file with its SHA-256. This tool maps that inventory onto the reviewed
component dispositions in ``docs/licensing/windows_portable_components.json`` and

* ``check``: fails closed when a shipped distribution, native binary or model file has no
  reviewed disposition or a model/font differs from its reviewed bytes; reports as
  blocked (``--allow-blocked`` for rehearsals) a shipped component that is not cleared
  for handoff, must not be shipped (``exclude``: removed at build time or installed by the
  recipient with ``PDFScoreBar.cmd setup``), or whose distribution version has not been
  license-reviewed yet, or whose first-party grant is for a different build manifest.
  Licenses are reviewed per distribution version, not per file
  digest: a compatible version update needs a license re-review, not new file hashes;
* ``bundle``: writes an *adjacent* compliance bundle (it never modifies the portable
  folder, its ``app/`` payload or ``verify --full`` inventory): license files copied
  from the folder, supplemental texts/sources from a private directory, a generated
  ``THIRD_PARTY_NOTICES.md``, ``COMPLIANCE_REPORT.json`` bound to the exact
  ``build_manifest.json`` digest, the optional Japanese trial guide, and
  ``SHA256SUMS``. Components that the recipient
  obtains directly from the official source at setup (``recipient_acquired``) are listed
  separately: they are not distributed by the folder's provider.

The policy is a record of reviewed facts, not legal advice. A ``cleared`` disposition
means the license terms and evidence were reviewed and the obligations are carried by the
bundle; it never stands for an owner's or recipient's acceptance. Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

POLICY_SCHEMA = "pdfscore.portable_compliance_policy.v1"
REPORT_SCHEMA = "pdfscore.portable_compliance_report.v1"
MANIFEST_SCHEMA = "pdfscore.windows_portable.build_manifest.v2"
# Dispositions that allow a handoff once their obligations are carried by the bundle.
HANDOFF_OK = {"cleared", "cleared_with_notice"}
DISPOSITIONS = HANDOFF_OK | {
    "permission_needed",
    "legal_interpretation_needed",
    "replace_or_retrain",
    "exclude",
}
# Files whose rights cannot be inferred from the owning Python distribution alone.
NATIVE_SUFFIXES = {".dll", ".exe", ".pyd", ".so", ".lib"}
MODEL_SUFFIXES = {".onnx", ".pth", ".pt", ".bin", ".ttf", ".otf"}
REPO = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = REPO / "docs" / "licensing" / "windows_portable_components.json"


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(files: dict[str, list]) -> str:
    lines = "".join(f"{name}\t{size}\t{digest}\n" for name, (size, digest) in sorted(files.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def load_manifest(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"Unsupported portable manifest: {manifest.get('schema_version')}")
    if tree_digest(manifest["files"]) != manifest["tree_digest"]:
        raise ValueError("Portable manifest file list does not match its tree digest")
    return manifest, sha256_bytes(raw)


def load_policy(path: Path) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema_version") != POLICY_SCHEMA:
        raise ValueError(f"Unsupported compliance policy: {policy.get('schema_version')}")
    components = policy["components"]
    problems = []
    guide = policy.get("trial_user_guide")
    if guide is not None and (
        not isinstance(guide, str)
        or not re.fullmatch(r"docs/windows_portable/[A-Za-z0-9_.-]+\.md", guide)
    ):
        problems.append("invalid trial_user_guide path")
    for cid, comp in components.items():
        if comp.get("disposition") not in DISPOSITIONS:
            problems.append(f"component {cid}: invalid disposition {comp.get('disposition')!r}")
        grant_scope = comp.get("grant_manifest_sha256")
        if grant_scope is not None and (
            not isinstance(grant_scope, str) or not re.fullmatch(r"[0-9a-f]{64}", grant_scope)
        ):
            problems.append(f"component {cid}: invalid grant_manifest_sha256")
        for item in comp.get("supplemental", []):
            if item.get("status") not in {"collected", "pending"}:
                problems.append(f"component {cid}: supplemental {item.get('name')} lacks status")
    for name, entry in policy["distributions"].items():
        if entry["component"] not in components:
            problems.append(f"distribution {name}: unknown component {entry['component']}")
    for rule in policy["file_rules"]:
        if rule["component"] not in components:
            problems.append(f"file rule {rule['pattern']}: unknown component {rule['component']}")
    if problems:
        raise ValueError("Invalid compliance policy:\n" + "\n".join(problems))
    return policy


def needs_rule(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in NATIVE_SUFFIXES or suffix in MODEL_SUFFIXES


def match_rule(path: str, rules: list[dict]) -> dict | None:
    for rule in rules:
        if fnmatch.fnmatchcase(path, rule["pattern"]):
            return rule
    return None


@dataclass
class Evaluation:
    errors: list[str] = field(default_factory=list)
    used: dict[str, dict] = field(default_factory=dict)  # component -> evidence
    blocked: dict[str, list[str]] = field(default_factory=dict)
    unreviewed_versions: dict[str, list[str]] = field(default_factory=dict)

    def use(self, cid: str, kind: str, item: str) -> None:
        self.used.setdefault(cid, {"distributions": [], "files": []})[kind].append(item)


def evaluate(manifest: dict, policy: dict, *, manifest_sha256: str | None = None) -> Evaluation:
    result = Evaluation()
    dists = policy["distributions"]
    for name, version in sorted(manifest.get("distributions", {}).items()):
        entry = dists.get(canonical(name))
        if entry is None:
            result.errors.append(
                f"shipped distribution without reviewed disposition: {name}=={version}"
            )
            continue
        if entry["version"] != version:
            result.unreviewed_versions.setdefault(entry["component"], []).append(
                f"license not reviewed for {name}=={version} (reviewed {entry['version']})"
            )
        result.use(entry["component"], "distributions", f"{name}=={version}")
    for path in sorted(manifest["files"]):
        if not needs_rule(path):
            continue
        rule = match_rule(path, policy["file_rules"])
        if rule is None:
            result.errors.append(f"shipped native/model file without reviewed disposition: {path}")
            continue
        if rule.get("sha256") and rule["sha256"] != manifest["files"][path][1]:
            result.errors.append(f"{path}: sha256 differs from the reviewed bytes")
            continue
        result.use(rule["component"], "files", path)
    for cid in sorted(result.used):
        comp = policy["components"][cid]
        reasons = list(result.unreviewed_versions.get(cid, []))
        # A build-scoped owner grant does not authorize other build identities.
        grant_scope = comp.get("grant_manifest_sha256")
        if grant_scope and manifest_sha256 != grant_scope:
            reasons.append(
                "owner grant limited to build manifest "
                f"{grant_scope}; actual manifest {manifest_sha256 or 'not provided'}"
            )
        if comp["disposition"] not in HANDOFF_OK:
            reasons.append(
                f"disposition {comp['disposition']}: {comp.get('open_issue', '')}".strip()
            )
        for item in comp.get("supplemental", []):
            if item["status"] != "collected":
                reasons.append(f"supplemental pending: {item['name']}")
        if reasons:
            result.blocked[cid] = reasons
    return result


def report(
    manifest: dict, manifest_sha: str, policy: dict, policy_sha: str, ev: Evaluation
) -> dict:
    return {
        "schema_version": REPORT_SCHEMA,
        "manifest_sha256": manifest_sha,
        "tree_digest": manifest["tree_digest"],
        "application_source_commit": manifest.get("application_source_commit"),
        "builder_source_commit": manifest.get("builder_source_commit"),
        "policy_sha256": policy_sha,
        "policy_reviewed": policy.get("reviewed"),
        "recipient_acquired": policy.get("recipient_acquired", []),
        "errors": ev.errors,
        "blocked": ev.blocked,
        "handoff_ready": not ev.errors and not ev.blocked,
        "components": {
            cid: {
                "title": policy["components"][cid]["title"],
                "license": policy["components"][cid]["license"],
                "disposition": policy["components"][cid]["disposition"],
                "evidence": evidence,
            }
            for cid, evidence in sorted(ev.used.items())
        },
    }


def cmd_check(args: argparse.Namespace) -> int:
    manifest, manifest_sha = load_manifest(args.manifest)
    policy = load_policy(args.policy)
    ev = evaluate(manifest, policy, manifest_sha256=manifest_sha)
    payload = report(manifest, manifest_sha, policy, sha256_file(args.policy), ev)
    if args.report:
        args.report.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    for line in ev.errors:
        print(f"ERROR {line}")
    for cid, reasons in ev.blocked.items():
        for reason in reasons:
            print(f"BLOCKED {cid}: {reason}")
    print(
        f"{len(ev.used)} shipped components, {len(ev.errors)} errors, "
        f"{len(ev.blocked)} blocked; handoff_ready={payload['handoff_ready']}"
    )
    if ev.errors:
        return 2
    if ev.blocked and not args.allow_blocked:
        return 1
    return 0


def notices_markdown(payload: dict, policy: dict) -> str:
    lines = [
        "# Third-party notices / 第三者通知",
        "",
        f"Portable build manifest SHA-256: `{payload['manifest_sha256']}`  ",
        f"Tree digest: `{payload['tree_digest']}`  ",
        f"Application source commit: `{payload['application_source_commit']}`",
        "",
        "Each component below is shipped in the portable folder. The license texts are in",
        "`licenses/<component>/` of this bundle (copied from the folder) and, where the",
        "shipped files lack them, in `supplemental/<component>/`. Corresponding source and",
        "written offers are described in `SOURCE.md`.",
        "",
        "| Component | License | Obligations |",
        "| --- | --- | --- |",
    ]
    for cid, comp in payload["components"].items():
        full = policy["components"][cid]
        obligations = "; ".join(full.get("obligations", [])) or "retain notices"
        lines.append(f"| {comp['title']} | {comp['license']} | {obligations} |")
    attributions = [
        (policy["components"][cid]["title"], policy["components"][cid]["attribution"])
        for cid in payload["components"]
        if policy["components"][cid].get("attribution")
    ]
    if attributions:
        lines += ["", "## Attributions", ""]
        lines += [f"- **{title}**: {text}" for title, text in attributions]
    acquired = payload.get("recipient_acquired", [])
    if acquired:
        lines += [
            "",
            "## Obtained by the recipient, not distributed with this folder",
            "",
            "`PDFScoreBar.cmd setup` downloads these from their official source into `addons/`;",
            "the recipient obtains them under the upstream terms below.",
            "",
            "| Package | Source | License / contents |",
            "| --- | --- | --- |",
        ]
        lines += [
            f"| {a['name']} {a['version']} | {a['source']} | {a['license']} |" for a in acquired
        ]
    return "\n".join(lines) + "\n"


def cmd_bundle(args: argparse.Namespace) -> int:
    manifest_path = args.root / "runtime" / "build_manifest.json"
    manifest, manifest_sha = load_manifest(manifest_path)
    policy = load_policy(args.policy)
    ev = evaluate(manifest, policy, manifest_sha256=manifest_sha)
    if ev.errors:
        for line in ev.errors:
            print(f"ERROR {line}")
        return 2
    out = args.out
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Output directory is not empty: {out}")
    if out.resolve().is_relative_to(args.root.resolve()):
        raise SystemExit(
            "The compliance bundle must be adjacent to, not inside, the portable folder"
        )
    out.mkdir(parents=True, exist_ok=True)
    files = manifest["files"]
    for cid in sorted(ev.used):
        comp = policy["components"][cid]
        for pattern in comp.get("notice_files", []):
            for rel in sorted(p for p in files if fnmatch.fnmatchcase(p, pattern)):
                source = args.root / rel
                if sha256_file(source) != files[rel][1]:
                    raise SystemExit(f"{rel}: folder bytes differ from the build manifest")
                target = out / "licenses" / cid / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for item in comp.get("supplemental", []):
            if item["status"] != "collected":
                continue
            source = (args.supplemental_dir / item["file"]) if args.supplemental_dir else None
            if source is None or not source.is_file():
                ev.blocked.setdefault(cid, []).append(f"supplemental missing: {item['file']}")
                continue
            if item.get("sha256") and sha256_file(source) != item["sha256"]:
                ev.blocked.setdefault(cid, []).append(f"supplemental hash mismatch: {item['file']}")
                continue
            target = out / "supplemental" / cid / Path(item["file"]).name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    # Keep the accepted build untouched; the recipient guide belongs to the adjacent
    # compliance bundle so the trial user can read it without repository access.
    guide = policy.get("trial_user_guide")
    if guide:
        source = REPO / guide
        if not source.is_file():
            raise SystemExit(f"Trial user guide missing from repository: {guide}")
        shutil.copyfile(source, out / "TRIAL_GUIDE.md")
    payload = report(manifest, manifest_sha, policy, sha256_file(args.policy), ev)
    (out / "COMPLIANCE_REPORT.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out / "THIRD_PARTY_NOTICES.md").write_text(notices_markdown(payload, policy), encoding="utf-8")
    source_md = policy.get("source_instructions")
    if source_md:
        (out / "SOURCE.md").write_text("\n".join(source_md) + "\n", encoding="utf-8")
    sums = [
        f"{sha256_file(p)}  {p.relative_to(out).as_posix()}"
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "SHA256SUMS"
    ]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"bundle written: {out} ({len(sums)} files); handoff_ready={payload['handoff_ready']}")
    return 0 if payload["handoff_ready"] or args.allow_blocked else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="map a build manifest onto reviewed dispositions")
    check.add_argument("manifest", type=Path)
    check.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    check.add_argument("--report", type=Path)
    check.add_argument(
        "--allow-blocked", action="store_true", help="rehearsal: exit 0 when only blocked"
    )
    check.set_defaults(func=cmd_check)
    bundle = sub.add_parser("bundle", help="write the adjacent compliance bundle")
    bundle.add_argument("root", type=Path, help="built portable folder")
    bundle.add_argument("out", type=Path, help="new directory beside the portable folder")
    bundle.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    bundle.add_argument("--supplemental-dir", type=Path)
    bundle.add_argument("--allow-blocked", action="store_true")
    bundle.set_defaults(func=cmd_bundle)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
