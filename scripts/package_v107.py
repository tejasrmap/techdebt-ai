import os
import shutil
import hashlib
import zipfile
import tempfile

def package_release():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    release_dir = os.path.join(base_dir, "release")
    staging_dir = os.path.join(release_dir, "techdebt-ai-v1.0.7")
    zip_path = os.path.join(release_dir, "techdebt-ai-v1.0.7-production.zip")

    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir, exist_ok=True)

    # 1. Root files
    root_files = ["README.md", "RELEASE_MANIFEST.md", "docker-compose.yml", ".env.example", "LICENSE"]
    for rf in root_files:
        src = os.path.join(base_dir, rf)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(staging_dir, rf))

    # 2. Docs directory
    shutil.copytree(os.path.join(base_dir, "docs"), os.path.join(staging_dir, "docs"))

    # 3. Backend directory (filtering caches and temporary databases)
    def backend_filter(dirpath, contents):
        ignored = set()
        for item in contents:
            if item in ["__pycache__", ".pytest_cache", "techdebt.db", "test.db", ".coverage"]:
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
        # Test ZIP integrity
        corrupt_file = zf.testzip()
        if corrupt_file:
            raise RuntimeError(f"Corrupt file in ZIP: {corrupt_file}")
        
        infolist = zf.infolist()
        backslash_entries = [info.filename for info in infolist if "\\" in info.filename]
        if backslash_entries:
            raise RuntimeError(f"ERROR: Found {len(backslash_entries)} entries with backslashes: {backslash_entries[:5]}")
        print("ALL ZIP entries verified with standard forward slashes ('/').")
        print("ZIP integrity test passed (testzip returned None).")

    # 7. Calculate SHA256 digest of actual ZIP file
    hasher = hashlib.sha256()
    with open(zip_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    zip_sha256 = hasher.hexdigest()
    print(f"ZIP SHA256: {zip_sha256}")

    # Write checksums
    checksum_line = f"{zip_sha256}  techdebt-ai-v1.0.7-production.zip\n"
    with open(os.path.join(release_dir, "SHA256SUMS.txt"), "w") as f:
        f.write(checksum_line)
    with open(os.path.join(release_dir, "SHA256SUMS"), "w") as f:
        f.write(checksum_line)
    with open(os.path.join(base_dir, "SHA256SUMS.txt"), "w") as f:
        f.write(f"{zip_sha256}  release/techdebt-ai-v1.0.7-production.zip\n")

    # 8. Test extract into clean temp directory
    with tempfile.TemporaryDirectory() as temp_extract:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_extract)
        extracted_files = []
        for r, d, fs in os.walk(temp_extract):
            for fl in fs:
                extracted_files.append(os.path.relpath(os.path.join(r, fl), temp_extract))
        print(f"Extraction test verified {len(extracted_files)} files in temporary directory.")
        assert len(extracted_files) == entry_count

    # Cleanup staging directory
    shutil.rmtree(staging_dir)
    print("Staging directory cleaned up.")
    print("Release v1.0.7 packaging completed successfully!")
    return zip_sha256

if __name__ == "__main__":
    package_release()

