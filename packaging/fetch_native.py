#!/usr/bin/env python3
"""Fetch and relocate the native tools bundled in the macOS app.

Run from the repository root:

    uv run python packaging/fetch_native.py

The script downloads Pandoc 3.14 (arm64), the Tiktoken ``cl100k_base``
cache, and the macOS 15 (Sequoia) Homebrew bottles for librsvg and
libemf2svg plus their actual dylib closure.  Everything is rewritten to
``@loader_path`` and copied into ``packaging/native``.

No GitHub CI, no macOS 15 machine and no Homebrew install is required beyond
the build machine's own tools (``otool``, ``install_name_tool``, ``codesign``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "packaging" / "native"
CACHE = ROOT / "packaging" / ".cache"
BOTTLE_CACHE = CACHE / "bottles"
DOWNLOAD_CACHE = CACHE / "downloads"

TARGET_TAG = "arm64_sequoia"
LIBRSVG_VERSION = "2.63.4_1"
LIBEMF2SVG_VERSION = "1.8.1"

PANDOC_VERSION = "3.14"
PANDOC_URL = (
    "https://github.com/jgm/pandoc/releases/download/3.14/"
    "pandoc-3.14-arm64-macOS.zip"
)
PANDOC_SHA256 = "58d6593884fec9d4424b641b92503c316d9c36decb2891ff8d73ae74dd3b6304"

TIKTOKEN_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
)
TIKTOKEN_SHA256 = (
    "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
)
TIKTOKEN_CACHE_NAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"

FONTS_CONF = """<?xml version="1.0"?>
<fontconfig>
  <dir>/System/Library/Fonts</dir>
  <dir>/System/Library/Fonts/Supplemental</dir>
  <dir>/Library/Fonts</dir>
  <dir>~/Library/Fonts</dir>
  <cachedir>~/Library/Caches/Copy4AI/fontconfig</cachedir>
</fontconfig>
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected: str | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        print(f"downloading {url}")
        with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    if expected:
        actual = sha256(destination)
        if actual != expected:
            destination.unlink(missing_ok=True)
            raise RuntimeError(
                f"checksum mismatch for {url}\nexpected {expected}\ngot      {actual}"
            )
    return destination


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def install_pandoc() -> None:
    archive = download(PANDOC_URL, DOWNLOAD_CACHE / "pandoc-3.14-arm64.zip", PANDOC_SHA256)
    target = NATIVE / "bin" / "pandoc"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        member = next(name for name in bundle.namelist() if name.endswith("/bin/pandoc"))
        with bundle.open(member) as source, target.open("wb") as handle:
            shutil.copyfileobj(source, handle)
    target.chmod(0o755)
    print(f"pandoc -> {target}")


def install_tiktoken_cache() -> None:
    blob = download(TIKTOKEN_URL, DOWNLOAD_CACHE / "cl100k_base.tiktoken", TIKTOKEN_SHA256)
    target = NATIVE / "tiktoken" / TIKTOKEN_CACHE_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(blob, target)
    print(f"tiktoken cache -> {target}")


# ---------------------------------------------------------------------------
# Homebrew bottles from GHCR
# ---------------------------------------------------------------------------


def _token(repository: str) -> str:
    quoted = urllib.parse.quote(repository, safe="/")
    url = f"https://ghcr.io/token?scope=repository:{quoted}:pull&service=ghcr.io"
    with urllib.request.urlopen(url) as response:
        return json.load(response)["token"]


def _get_json(repository: str, path: str, accept: str, token: str):
    request = urllib.request.Request(
        f"https://ghcr.io/v2/{repository}/{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": accept},
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def _get_bytes(repository: str, path: str, token: str) -> bytes:
    request = urllib.request.Request(
        f"https://ghcr.io/v2/{repository}/{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "*/*"},
    )
    with urllib.request.urlopen(request) as response:
        return response.read()


def repo_for_formula(formula: str) -> str:
    if "@" in formula:
        base, version = formula.split("@", 1)
        return f"homebrew/core/{base}/{version}"
    return f"homebrew/core/{formula}"


def fetch_bottle(formula: str, version: str) -> tuple[Path, dict]:
    """Fetch one formula bottle and return its extraction root and tab."""
    root = BOTTLE_CACHE / formula / version
    marker = root / ".fetched"
    if marker.exists():
        tab = json.loads((root / ".tab.json").read_text())
        return root, tab

    repository = repo_for_formula(formula)
    token = _token(repository)
    print(f"resolving {formula} {version} ({TARGET_TAG})")
    manifest = _get_json(
        repository,
        f"manifests/{urllib.parse.quote(version, safe='')}",
        "application/vnd.oci.image.index.v1+json, "
        "application/vnd.docker.distribution.manifest.list.v2+json, "
        "application/vnd.oci.image.manifest.v1+json",
        token,
    )

    if "manifests" in manifest:
        selected = None
        for candidate in manifest["manifests"]:
            ref = candidate.get("annotations", {}).get(
                "org.opencontainers.image.ref.name", ""
            )
            if ref.endswith(f".{TARGET_TAG}"):
                selected = candidate
                break
        if selected is None:
            raise RuntimeError(f"no {TARGET_TAG} bottle for {formula} {version}")
        manifest = _get_json(
            repository,
            f"manifests/{selected['digest']}",
            "application/vnd.oci.image.manifest.v1+json",
            token,
        )

    tab_raw = manifest.get("annotations", {}).get("sh.brew.tab")
    if not tab_raw:
        raise RuntimeError(f"no Homebrew tab metadata for {formula} {version}")
    tab = json.loads(tab_raw)

    layer = manifest["layers"][0]
    blob = _get_bytes(repository, f"blobs/{layer['digest']}", token)
    archive = DOWNLOAD_CACHE / f"{formula}-{version}-{TARGET_TAG}.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(blob)

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:gz") as bundle:
        bundle.extractall(root, filter="data")
    (root / ".tab.json").write_text(json.dumps(tab))
    marker.write_text("ok")
    return root, tab


def dependency_versions() -> tuple[dict[str, str], callable]:
    versions: dict[str, str] = {}

    def add(tab: dict) -> None:
        for dep in tab.get("runtime_dependencies", []):
            versions.setdefault(dep["full_name"], dep["pkg_version"])

    return versions, add


def scan_formula_dependencies(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            proc = run("otool", "-L", str(path), check=False)
        except OSError:
            continue
        if proc.returncode != 0:
            continue
        for dep in parse_otool(proc.stdout):
            name = dependency_formula_name(dep)
            if name:
                names.add(name)
    return names


def parse_otool(output: str) -> list[str]:
    deps: list[str] = []
    for line in output.splitlines()[1:]:
        match = re.match(r"\s+(.+?) \(compatibility", line)
        if match:
            deps.append(match.group(1))
    return deps


def dependency_formula_name(path: str) -> str | None:
    for marker in ("@@HOMEBREW_PREFIX@@/opt/", "/opt/homebrew/opt/"):
        if marker in path:
            return path.split(marker, 1)[1].split("/", 1)[0]
    for marker in ("@@HOMEBREW_CELLAR@@/", "/opt/homebrew/Cellar/"):
        if marker in path:
            parts = path.split(marker, 1)[1].split("/")
            if len(parts) >= 2:
                return parts[0]
    return None


def fetch_dependency_graph(root_formula: str, root_version: str) -> tuple[Path, dict[str, Path]]:
    versions, add_versions = dependency_versions()
    fetched: dict[str, Path] = {}
    queue: list[str] = [root_formula]

    while queue:
        formula = queue.pop(0)
        if formula in fetched:
            continue
        version = root_version if formula == root_formula else versions.get(formula)
        if not version:
            raise RuntimeError(f"no version recorded for dependency {formula}")
        root, tab = fetch_bottle(formula, version)
        add_versions(tab)
        fetched[formula] = root
        for dependency in scan_formula_dependencies(root):
            if dependency not in fetched and dependency not in queue:
                queue.append(dependency)

    return fetched[root_formula], fetched


def dylib_index(extracted: dict[str, Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for root in extracted.values():
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix != ".dylib" and not path.is_symlink():
                continue
            resolved = path.resolve()
            name = path.name
            if name in index and index[name] != resolved:
                raise RuntimeError(f"duplicate dylib name: {name}")
            index[name] = resolved
    return index


def collect_aliases(extracted: dict[str, Path]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for root in extracted.values():
        for path in root.rglob("*"):
            if path.is_symlink():
                target = path.resolve()
                if target.name.endswith(".dylib"):
                    aliases[path.name] = target.name
    return aliases


def file_closure(executables: list[Path], index: dict[str, Path]) -> list[Path]:
    needed: dict[Path, None] = {}
    pending = list(executables)
    while pending:
        path = pending.pop()
        resolved = path.resolve()
        if resolved in needed:
            continue
        needed[resolved] = None
        proc = run("otool", "-L", str(path), check=False)
        if proc.returncode != 0:
            continue
        for dep in parse_otool(proc.stdout):
            if dependency_formula_name(dep) is None and not dep.startswith("@rpath/"):
                continue
            name = Path(dep).name
            dependency = index.get(name)
            if dependency is None:
                raise RuntimeError(f"missing dylib {name} required by {path}")
            pending.append(dependency)
    return list(needed)


def copy_and_relocate(
    files: list[Path],
    executable_names: set[str],
    aliases: dict[str, str],
) -> None:
    target = NATIVE / "bin"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    copied: dict[str, Path] = {}
    for source in files:
        source = source.resolve()
        destination = target / source.name
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if source.name in executable_names else 0o644)
        copied[source.name] = destination

    for alias, real_name in aliases.items():
        if real_name in copied and alias not in copied:
            (target / alias).symlink_to(real_name)

    for name, path in copied.items():
        run("codesign", "--remove-signature", str(path), check=False)

    for name, path in copied.items():
        proc = run("otool", "-L", str(path), check=False)
        deps = parse_otool(proc.stdout) if proc.returncode == 0 else []
        for dep in deps:
            dep_name = Path(dep).name
            real_name = aliases.get(dep_name, dep_name)
            if real_name in copied:
                run(
                    "install_name_tool",
                    "-change",
                    dep,
                    f"@loader_path/{real_name}",
                    str(path),
                )
        if path.suffix == ".dylib":
            run("install_name_tool", "-id", f"@loader_path/{name}", str(path))
        run("codesign", "--force", "--sign", "-", str(path))

    for name, path in copied.items():
        proc = run("otool", "-L", str(path))
        if "@@HOMEBREW" in proc.stdout or "/opt/homebrew" in proc.stdout:
            raise RuntimeError(f"{name} still references Homebrew")


def build_native_tools() -> None:
    extracted_all: dict[str, Path] = {}
    for formula, version in (
        ("librsvg", LIBRSVG_VERSION),
        ("libemf2svg", LIBEMF2SVG_VERSION),
    ):
        _root, extracted = fetch_dependency_graph(formula, version)
        for name, path in extracted.items():
            extracted_all.setdefault(name, path)

    index = dylib_index(extracted_all)
    aliases = collect_aliases(extracted_all)
    executables = [
        extracted_all["librsvg"]
        / "librsvg"
        / LIBRSVG_VERSION
        / "bin"
        / "rsvg-convert",
        extracted_all["libemf2svg"]
        / "libemf2svg"
        / LIBEMF2SVG_VERSION
        / "bin"
        / "emf2svg-conv",
    ]
    for executable in executables:
        if not executable.exists():
            raise RuntimeError(f"missing bottle executable: {executable}")

    files = file_closure(executables, index)
    copy_and_relocate(files, {"rsvg-convert", "emf2svg-conv"}, aliases)
    print(f"native tools -> {NATIVE / 'bin'} ({len(files)} files)")


def install_fontconfig() -> None:
    target = NATIVE / "etc" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    (target / "fonts.conf").write_text(FONTS_CONF)
    print(f"fonts.conf -> {target / 'fonts.conf'}")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("this build step only runs on macOS")
    for command in ("otool", "install_name_tool", "codesign"):
        if not shutil.which(command):
            raise SystemExit(f"missing required tool: {command}")

    NATIVE.mkdir(parents=True, exist_ok=True)
    install_tiktoken_cache()
    build_native_tools()
    install_pandoc()
    install_fontconfig()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
