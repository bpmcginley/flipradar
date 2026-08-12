"""Static repo audit for a freshly acquired codebase.

audit_repo(path) walks the repo (no network, no code execution) and returns a
markdown report: size and language breakdown, health checks (tests / CI /
LICENSE / README / Dockerfile), dependency manifests with dependency counts,
TODO/FIXME/HACK debt count, largest files, and secrets-ish patterns that must
be rotated after purchase.

The "Health checks" section uses stable `<name>: present|missing` lines so
refurb.plan can parse the report and tailor the 90-day plan.

CLI:
    python -m refurb.audit <path> [--out report.md]
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone

log = logging.getLogger("flipradar.refurb.audit")

# Directories that are build output / vendored code, not the product.
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist",
    "build", ".next", ".nuxt", "target", "vendor", "bower_components",
    ".idea", ".vscode", "coverage", ".cache", "bin", "obj",
}

# Extensions we treat as text and scan for TODOs / secrets.
TEXT_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".rb", ".php",
    ".go", ".rs", ".java", ".kt", ".cs", ".c", ".h", ".cpp", ".hpp",
    ".swift", ".sh", ".ps1", ".bat", ".sql", ".html", ".htm", ".css",
    ".scss", ".less", ".vue", ".svelte", ".md", ".rst", ".txt", ".toml",
    ".ini", ".cfg", ".conf", ".yaml", ".yml", ".json", ".xml", ".env",
    ".example", ".tf", ".dockerfile", ".liquid", ".erb", ".ejs",
}

MAX_SCAN_BYTES = 1_000_000  # skip content scan of files larger than this

TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")

# Secrets-ish patterns. Matches are flagged for rotation, values never printed.
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("hardcoded credential assignment",
     re.compile(r"""(?i)\b(api[_-]?key|apikey|secret|token|passwd|password|auth[_-]?key)\b\s*[=:]\s*["'][^"'\s]{8,}["']""")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Stripe live secret key", re.compile(r"\bsk_live_[0-9A-Za-z]{10,}")),
    ("Stripe test secret key", re.compile(r"\bsk_test_[0-9A-Za-z]{10,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("connection string with password",
     re.compile(r"(?i)\b\w+://[^/\s:@]+:[^@\s]{4,}@[\w.-]+")),
]

# Manifest filename -> (ecosystem, dependency counter).
# Counters are heuristic line/key counts, not full parsers.


def _count_requirements(text: str) -> int:
    n = 0
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-r", "--")):
            n += 1
    return n


def _count_package_json(text: str) -> int:
    import json

    try:
        data = json.loads(text)
    except ValueError:
        return 0
    return len(data.get("dependencies", {})) + len(data.get("devDependencies", {}))


def _count_toml_deps(text: str) -> int:
    """Rough dep count for pyproject.toml / Cargo.toml / Pipfile."""
    n = 0
    in_dep_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.strip("[]").lower()
            in_dep_section = "dependencies" in section or section in ("packages", "dev-packages")
            continue
        if in_dep_section and stripped and not stripped.startswith("#") and "=" in stripped:
            n += 1
    # pyproject PEP 621 style: dependencies = ["a", "b"]
    m = re.search(r"(?s)^dependencies\s*=\s*\[(.*?)\]", text, re.MULTILINE)
    if m:
        n += len(re.findall(r"[\"']", m.group(1))) // 2
    return n


def _count_gemfile(text: str) -> int:
    return len(re.findall(r"(?m)^\s*gem\s+[\"']", text))


def _count_go_mod(text: str) -> int:
    return len(re.findall(r"(?m)^\s+[\w./-]+\s+v[\d.]", text))


def _count_csproj(text: str) -> int:
    return len(re.findall(r"<PackageReference\b", text))


MANIFESTS = {
    "requirements.txt": ("python", _count_requirements),
    "requirements-dev.txt": ("python", _count_requirements),
    "pyproject.toml": ("python", _count_toml_deps),
    "Pipfile": ("python", _count_toml_deps),
    "package.json": ("node", _count_package_json),
    "Gemfile": ("ruby", _count_gemfile),
    "go.mod": ("go", _count_go_mod),
    "Cargo.toml": ("rust", _count_toml_deps),
    "composer.json": ("php", _count_package_json),
}


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n / 1:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} GB"


def _walk(path: str):
    """Yield (abs_path, rel_path, size) for every non-skipped file."""
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git")]
        for name in files:
            full = os.path.join(root, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            yield full, os.path.relpath(full, path), size


def _is_test_file(rel: str) -> bool:
    parts = rel.replace("\\", "/").lower().split("/")
    name = parts[-1]
    if any(p in ("tests", "test", "spec", "__tests__") for p in parts[:-1]):
        return True
    return (name.startswith("test_") or name.endswith(("_test.py", "_test.go"))
            or ".test." in name or ".spec." in name)


def audit_repo(path: str) -> str:
    """Audit a repo directory and return a markdown report (static checks only)."""
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        raise ValueError(f"not a directory: {path}")

    total_size = 0
    file_count = 0
    by_ext: dict[str, tuple[int, int]] = {}  # ext -> (files, bytes)
    largest: list[tuple[int, str]] = []
    manifests_found: list[tuple[str, str, int]] = []  # rel, ecosystem, dep count
    todo_count = 0
    todo_files = 0
    secret_hits: list[tuple[str, int, str]] = []  # rel, line no, pattern label
    has_tests = False
    has_ci = False
    has_license = False
    has_readme = False
    has_docker = False

    for full, rel, size in _walk(path):
        total_size += size
        file_count += 1
        name = os.path.basename(rel)
        lower = name.lower()
        ext = os.path.splitext(lower)[1] or "(none)"
        f, b = by_ext.get(ext, (0, 0))
        by_ext[ext] = (f + 1, b + size)
        largest.append((size, rel))

        rel_norm = rel.replace("\\", "/")
        if _is_test_file(rel):
            has_tests = True
        if (rel_norm.startswith((".github/workflows/", ".circleci/"))
                or lower in ("jenkinsfile", ".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml")):
            has_ci = True
        if lower.startswith("license") or lower.startswith("copying"):
            has_license = True
        if lower.startswith("readme"):
            has_readme = True
        if lower == "dockerfile" or lower.startswith("docker-compose") or ext == ".dockerfile":
            has_docker = True

        if name in MANIFESTS and size <= MAX_SCAN_BYTES:
            eco, counter = MANIFESTS[name]
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    manifests_found.append((rel_norm, eco, counter(fh.read())))
            except OSError as exc:
                log.warning("could not read manifest %s: %s", rel, exc)

        if ext in TEXT_EXTS and size <= MAX_SCAN_BYTES:
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    file_todos = 0
                    for lineno, line in enumerate(fh, 1):
                        file_todos += len(TODO_RE.findall(line))
                        for label, pat in SECRET_PATTERNS:
                            if pat.search(line):
                                secret_hits.append((rel_norm, lineno, label))
                    if file_todos:
                        todo_count += file_todos
                        todo_files += 1
            except OSError as exc:
                log.warning("could not scan %s: %s", rel, exc)

    largest.sort(reverse=True)
    ext_rows = sorted(by_ext.items(), key=lambda kv: kv[1][1], reverse=True)

    lines: list[str] = []
    add = lines.append
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    add(f"# Repo Audit: {os.path.basename(path) or path}")
    add("")
    add(f"- Path: `{path}`")
    add(f"- Generated: {now} (FlipRadar refurb.audit, static checks only)")
    add(f"- Files: {file_count:,} | Total size: {_fmt_size(total_size)} "
        "(build output / vendored dirs excluded)")
    add("")

    add("## Language / extension breakdown")
    add("")
    add("| Extension | Files | Size | % of bytes |")
    add("|---|---:|---:|---:|")
    for ext, (f, b) in ext_rows[:12]:
        pct = (b / total_size * 100) if total_size else 0
        add(f"| `{ext}` | {f:,} | {_fmt_size(b)} | {pct:.1f}% |")
    if len(ext_rows) > 12:
        add(f"| ... {len(ext_rows) - 12} more | | | |")
    add("")

    add("## Health checks")
    add("")
    add(f"- Tests: {'present' if has_tests else 'missing'}")
    add(f"- CI: {'present' if has_ci else 'missing'}")
    add(f"- LICENSE: {'present' if has_license else 'missing'}")
    add(f"- README: {'present' if has_readme else 'missing'}")
    add(f"- Dockerfile: {'present' if has_docker else 'missing'}")
    add("")

    add("## Dependency manifests")
    add("")
    if manifests_found:
        for rel, eco, count in sorted(manifests_found):
            add(f"- `{rel}` ({eco}): ~{count} dependencies")
    else:
        add("- none found -- how does this thing deploy? Ask the seller.")
    add("")

    add("## Code debt markers")
    add("")
    add(f"- TODO/FIXME/HACK/XXX: {todo_count} across {todo_files} files")
    add("")

    add("## Largest files")
    add("")
    for size, rel in largest[:10]:
        add(f"- {_fmt_size(size)}  `{rel.replace(os.sep, '/')}`")
    add("")

    add("## Secrets-ish patterns (rotate after purchase)")
    add("")
    if secret_hits:
        add(f"{len(secret_hits)} potential secret(s) found. Values are NOT shown here.")
        add("Every one of these must be rotated on day 1 of ownership -- the seller")
        add("(and anyone they shared the repo with) has seen them.")
        add("")
        for rel, lineno, label in secret_hits[:50]:
            add(f"- `{rel}:{lineno}` -- {label}")
        if len(secret_hits) > 50:
            add(f"- ... {len(secret_hits) - 50} more")
    else:
        add("- none matched (heuristic scan; still rotate all credentials at handover)")
    add("")

    add("---")
    add("*Generated by FlipRadar refurb.audit. Heuristic static analysis; "
        "verify findings manually.*")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m refurb.audit",
        description="Static audit of an acquired repo -> markdown report.",
    )
    parser.add_argument("path", help="path to the repo to audit")
    parser.add_argument("--out", default=None, help="write report to this file instead of stdout")
    args = parser.parse_args(argv)

    try:
        report = audit_repo(args.path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(args.out)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
