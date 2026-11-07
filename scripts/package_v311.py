import os
import shutil
import hashlib
import zipfile
import tempfile

def package_release():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    release_dir = os.path.join(base_dir, "release")
    staging_dir = os.path.join(release_dir, "techdebt-ai-v3.1.1")
    zip_path = os.path.join(release_dir, "techdebt-ai-v3.1.1-production.zip")

    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir, exist_ok=True)
    os.makedirs(release_dir, exist_ok=True)

    # 1. Root files
    root_files = ["README.md", "RELEASE_MANIFEST.md", "docker-compose.yml", ".env.example", "LICENSE", "CHANGELOG.md"]
    for rf in root_files:
        src = os.path.join(base_dir, rf)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(staging_dir, rf))

    # 2. Docs directory
    docs_src = os.path.join(base_dir, "docs")
    if os.path.exists(docs_src):
        shutil.copytree(docs_src, os.path.join(staging_dir, "docs"))

    # 3. Backend directory (filtering caches, venvs, and temporary databases)
    def backend_filter(dirpath, contents):
        ignored = set()
        for item in contents:
            if item in ["__pycache__", ".pytest_cache", "techdebt.db", "test.db", ".coverage", "venv", ".venv"]:
                ignored.add(item)
            elif item.endswith((".db", ".sqlite", ".pyc", ".pyo")):
                ignored.add(item)
        return ignored

    shutil.copytree(
        os.path.join(base_dir, "backend"),
        os.path.join(staging_dir, "backend"),
        ignore=backend_filter
    )

    # 4. Frontend directory (filtering node_modules, dist, .cache)
    def frontend_filter(dirpath, contents):
        ignored = set()
        for item in contents:
            if item in ["node_modules", "dist", ".cache", ".rolldown_cache", ".vite"]:
                ignored.add(item)
        return ignored

    shutil.copytree(
        os.path.join(base_dir, "frontend"),
        os.path.join(staging_dir, "frontend"),
        ignore=frontend_filter
    )

    # 5. Build ZIP archive with strictly normalized forward-slash paths
    if os.path.exists(zip_path):
        os.remove(zip_path)

    seen_entries = set()
    entry_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(staging_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, staging_dir)
                # CRITICAL: Force standard POSIX forward slashes in ZIP entry name
                arcname = rel_path.replace("\\", "/")

                # Invariant checks
                assert arcname not in seen_entries, f"Duplicate entry: {arcname}"
                assert not arcname.startswith("/"), f"Absolute path detected: {arcname}"
                assert ".." not in arcname, f"Parent traversal detected: {arcname}"
                assert not arcname.endswith(".env"), f"Actual .env file detected: {arcname}"
                assert "node_modules" not in arcname, f"node_modules detected: {arcname}"
                assert "__pycache__" not in arcname, f"__pycache__ detected: {arcname}"
                assert not arcname.endswith((".db", ".sqlite")), f"Database file detected: {arcname}"

                zf.write(full_path, arcname)
                seen_entries.add(arcname)
                entry_count += 1

    print(f"Archived {entry_count} files into {zip_path}")

    # 6. Verify ZIP entry path format and integrity
    with zipfile.ZipFile(zip_path, "r") as zf:
        corrupt_file = zf.testzip()
        if corrupt_file:
            raise RuntimeError(f"Corrupt file in ZIP: {corrupt_file}")

        infolist = zf.infolist()
        backslash_entries = [info.filename for info in infolist if "\\" in info.filename]
        if backslash_entries:
            raise RuntimeError(f"ERROR: Found {len(backslash_entries)} entries with backslashes: {backslash_entries[:5]}")
        print("ALL ZIP entries verified with standard forward slashes ('/').")
        print("ZIP integrity test passed (testzip returned None).")

    # 7. Compute SHA256
    hasher = hashlib.sha256()
    with open(zip_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    zip_sha256 = hasher.hexdigest()
    zip_size_bytes = os.path.getsize(zip_path)
    zip_filename = os.path.basename(zip_path)

    print(f"Package SHA-256: {zip_sha256}")
    print(f"Package Size: {zip_size_bytes} bytes ({zip_size_bytes / (1024*1024):.2f} MB)")

    # 8. Test clean unpack into temporary directory
    with tempfile.TemporaryDirectory() as test_unpack_dir:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(test_unpack_dir)
        # Verify essential files exist
        assert os.path.exists(os.path.join(test_unpack_dir, "README.md"))
        assert os.path.exists(os.path.join(test_unpack_dir, "backend", "app", "main.py"))
        assert os.path.exists(os.path.join(test_unpack_dir, "frontend", "package.json"))
        assert os.path.exists(os.path.join(test_unpack_dir, "docker-compose.yml"))
        print("Test unpack into clean temporary directory succeeded!")

    # 9. Clean up staging directory
    shutil.rmtree(staging_dir)

    return zip_filename, zip_sha256, zip_size_bytes

if __name__ == "__main__":
    fname, sha, sz = package_release()
    print(f"\nFinal Package: {fname}")
    print(f"SHA-256: {sha}")
