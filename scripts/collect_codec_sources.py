"""Check the bundled PyAV DLLs and collect their corresponding source package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath


SCRIPTS = Path(__file__).resolve().parent
REPOSITORY = SCRIPTS.parent
PYAV_WHEEL = {
    "filename": "av-19.0.2-cp312-abi3-win_amd64.whl",
    "url": ("https://files.pythonhosted.org/packages/32/5a/"
            "743a83666ded197df8b9957e2800bef9a39d52b23be2ca211bbd14b5fb22/av-19.0.2-cp312-abi3-win_amd64.whl"),
    "sha256": "3ce5a1d7b916d13c16ac58f1756f0fee4af2d53f02bc1403e18550b50d375a22",
}
PYTHON_PACKAGES = (
    "aiortc", "aioice", "av", "cffi", "cryptography", "dnspython", "google-crc32c", "ifaddr",
    "mss", "Pillow", "PyAudioWPatch", "pycparser", "pyee", "pylibsrtp", "pyOpenSSL", "pyinstaller",
)
LICENSE_NAMES = ("author", "copying", "copyright", "license", "licence", "notice", "patents")


def file_hash(path):
    with path.open("rb") as value:
        return hashlib.file_digest(value, "sha256").hexdigest()


def download(entry, cache):
    path = cache / entry["filename"]
    if path.is_file() and file_hash(path) == entry["sha256"]:
        return path
    partial = path.with_suffix(path.suffix + ".part")
    try:
        subprocess.run([
            "curl.exe", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
            "--connect-timeout", "15", "--max-time", "120", "--output", str(partial), entry["url"],
        ], check=True)
        observed = file_hash(partial)
        if observed != entry["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {path.name}: expected {entry['sha256']}, got {observed}")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def verify_bundled_wheel(bundle, wheel_path):
    if importlib.metadata.version("av") != "19.0.2":
        raise RuntimeError("The public Windows packages require the audited PyAV 19.0.2 wheel.")
    library_directory = bundle / "_internal" / "av.libs"
    with zipfile.ZipFile(wheel_path) as wheel:
        expected = {item.filename.split("/")[-1]: item for item in wheel.infolist()
                    if item.filename.startswith("av.libs/") and item.filename.endswith(".dll")}
        actual = {path.name for path in library_directory.glob("*.dll")}
        if not expected or expected.keys() != actual:
            raise RuntimeError("The bundled codec DLL list differs from the audited Windows PyAV wheel.")
        for name, item in expected.items():
            with wheel.open(item) as stream:
                expected_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if file_hash(library_directory / name) != expected_hash:
                raise RuntimeError(f"The bundled codec DLL differs from the audited PyAV wheel: {name}")


def collect_licenses(bundle, archives):
    directory = bundle / "THIRD-PARTY-LICENSES"
    directory.mkdir(exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, directory / "Python-LICENSE.txt")
    for name in PYTHON_PACKAGES:
        package = importlib.metadata.distribution(name)
        for item in package.files or ():
            filename = item.name
            if not filename.casefold().startswith(LICENSE_NAMES) or item.suffix.casefold() in {".py", ".pyc"}:
                continue
            source = item.locate()
            if source.is_file():
                shutil.copyfile(source, directory / f"{name}-{filename}")

    for name, path in archives.items():
        if path.suffix == ".txt":
            shutil.copyfile(path, directory / path.name)
        elif path.suffix != ".zst":
            with tarfile.open(path) as archive:
                for member in archive:
                    parts = PurePosixPath(member.name).parts[1:]
                    if (not member.isfile() or not 1 <= len(parts) <= 3 or member.size > 500_000
                            or not parts[-1].casefold().startswith(LICENSE_NAMES)
                            or any(part in (".", "..") for part in parts)):
                        continue
                    license_name = name + "-" + "-".join(parts)
                    with archive.extractfile(member) as source:
                        (directory / license_name).write_bytes(source.read())
    return directory


def app_source_files():
    source_paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPOSITORY,
    ).decode("utf-8").split("\0")
    for name in sorted(set(source_paths)):
        root = name.split("/", 1)[0]
        if root not in {"scripts", "web", "tests", ".github"} and not (
            "/" not in name and (name.endswith((".py", ".md", ".iss", ".txt")) or name in {".gitignore", "LICENSE"})
        ):
            continue
        path = REPOSITORY / name
        if path.is_file():
            yield name, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("cache", type=Path)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    notices = REPOSITORY / "THIRD-PARTY-NOTICES.txt"
    manifest_path = SCRIPTS / "codec-sources.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        wheel = pool.submit(download, PYAV_WHEEL, args.cache)
        transfers = {name: pool.submit(download, entry, args.cache) for name, entry in manifest.items()}
        verify_bundled_wheel(args.bundle, wheel.result())
        archives = {name: transfer.result() for name, transfer in transfers.items()}

    licenses = collect_licenses(args.bundle, archives)
    shutil.copyfile(notices, args.bundle / notices.name)
    target = args.output / "TVPCCast-Codec-Sources.zip"
    partial = target.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(partial, "w") as archive:
            archive.write(SCRIPTS / "CODEC-SOURCE-README.txt", "CODEC-SOURCE-README.txt", zipfile.ZIP_DEFLATED)
            archive.write(notices, notices.name, zipfile.ZIP_DEFLATED)
            archive.write(manifest_path, "codec-sources.json", zipfile.ZIP_DEFLATED)
            archive.writestr("pyav-windows-wheel.json", json.dumps(PYAV_WHEEL, indent=2) + "\n")
            for source in archives.values():
                archive.write(source, f"upstream/{source.name}")
            for license_path in sorted(licenses.iterdir()):
                archive.write(license_path, f"THIRD-PARTY-LICENSES/{license_path.name}", zipfile.ZIP_DEFLATED)
            for name, path in app_source_files():
                archive.write(path, f"TVPCCast-source/{name}", zipfile.ZIP_DEFLATED)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    print(f"Corresponding codec source: {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
