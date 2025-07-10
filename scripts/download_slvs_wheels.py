#!/usr/bin/env python3
"""
Script to download Python wheel files for the slvs package.
Updates the wheels section in blender_manifest.toml with the downloaded files.

Usage:
  python download_slvs_wheels.py [--test-pypi] [--version VERSION] [--py-version PY_VERSION]

Options:
  --test-pypi           Download from Test PyPI instead of PyPI
  --version VERSION     Download a specific version instead of the latest
  --py-version VERSION  Python version to download wheels for (e.g., 3.11, 3.10-3.12)
"""

import os
import sys
import json
import urllib.request
import urllib.error
from urllib.parse import urljoin
import re
import importlib
import subprocess
import argparse

# Package name to download
PACKAGE_NAME = "slvs"

# Directory paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "wheels")
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "blender_manifest.toml")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Download Python wheel files for the slvs package.')
    parser.add_argument('--test-pypi', action='store_true',
                        help='Download from Test PyPI instead of PyPI')
    parser.add_argument('--version', type=str,
                        help='Download a specific version instead of the latest')
    parser.add_argument('--py-version', type=str, default='3.11',
                        help='Python version to download wheels for (e.g., 3.11, 3.10-3.12)')
    return parser.parse_args()

def get_json_api_url(test_pypi=False):
    """Get the JSON API URL based on whether to use Test PyPI or not."""
    if test_pypi:
        return f"https://test.pypi.org/pypi/{PACKAGE_NAME}/json"
    else:
        return f"https://pypi.org/pypi/{PACKAGE_NAME}/json"

def create_download_dir():
    """Create the download directory if it doesn't exist."""
    if not os.path.exists(DOWNLOAD_DIR):
        print(f"Creating download directory: {DOWNLOAD_DIR}")
        os.makedirs(DOWNLOAD_DIR)

def get_package_info(test_pypi=False):
    """Get package information from PyPI or Test PyPI."""
    json_api_url = get_json_api_url(test_pypi)
    source = "Test PyPI" if test_pypi else "PyPI"

    try:
        print(f"Fetching package information for {PACKAGE_NAME} from {source}...")
        with urllib.request.urlopen(json_api_url) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"Error fetching package information from {source}: {e}")
        sys.exit(1)

def download_file(url, filename):
    """Download a file from the given URL and save it to the specified filename."""
    try:
        print(f"Downloading {url}...")
        with urllib.request.urlopen(url) as response, open(filename, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        print(f"Successfully downloaded {os.path.basename(filename)}")
        return True
    except urllib.error.URLError as e:
        print(f"Error downloading {url}: {e}")
        return False

def parse_python_version_range(version_spec):
    """Parse Python version specification into a range.

    Args:
        version_spec: String like '3.11' or '3.9-3.11'

    Returns:
        Tuple of (min_version, max_version) as tuples of integers
    """
    if '-' in version_spec:
        min_ver_str, max_ver_str = version_spec.split('-')
        min_ver = tuple(map(int, min_ver_str.split('.')))
        max_ver = tuple(map(int, max_ver_str.split('.')))
    else:
        ver = tuple(map(int, version_spec.split('.')))
        min_ver = ver
        max_ver = ver

    # Ensure we have at least major.minor
    if len(min_ver) == 1:
        min_ver = (min_ver[0], 0)
    if len(max_ver) == 1:
        max_ver = (max_ver[0], 0)

    return min_ver, max_ver

def is_python_version_compatible(filename, py_version_spec):
    """Check if the wheel file is compatible with the specified Python version.

    This function checks the wheel filename which follows PEP 427 naming convention:
    {distribution}-{version}(-{build tag})?-{python tag}-{abi tag}-{platform tag}.whl

    Args:
        filename: Wheel filename
        py_version_spec: Python version specification (e.g., '3.11' or '3.9-3.11')
    """
    # Extract the Python tag (e.g., 'cp311', 'py3', etc.)
    match = re.search(r'-([^-]+)-([^-]+)-([^-]+)\.whl$', filename)
    if not match:
        return False

    python_tag = match.group(1)
    abi_tag = match.group(2)

    # Parse the version range
    min_version, max_version = parse_python_version_range(py_version_spec)

    # Handle pure Python wheels (py3)
    if python_tag == 'py3' and abi_tag == 'none':
        return True

    # Handle CPython specific wheels (cp3XX)
    if python_tag.startswith('cp'):
        # Extract the Python version from the tag (e.g., 'cp311' -> (3, 11))
        try:
            # Format could be 'cp311' (CPython 3.11) or 'cp37m' (CPython 3.7 with pymalloc)
            version_str = python_tag[2:]

            # Handle tags like 'cp37m' by removing the 'm' suffix
            version_str = re.sub(r'[^0-9]', '', version_str)

            if len(version_str) >= 2:
                major = int(version_str[0])
                minor = int(version_str[1:])
                wheel_version = (major, minor)

                # Check if the wheel version is within the specified range
                return min_version <= wheel_version <= max_version
        except ValueError:
            # If we can't parse the version, be conservative and return False
            return False

    return False

def update_manifest(downloaded_files):
    """Update the wheels section in the manifest file without using the toml package."""
    try:
        print(f"Updating manifest file: {MANIFEST_PATH}")

        # Read the manifest file
        with open(MANIFEST_PATH, 'r') as f:
            content = f.readlines()

        # Find the wheels section
        wheels_start = -1
        wheels_end = -1

        for i, line in enumerate(content):
            if line.strip() == "wheels = [":
                wheels_start = i
            elif wheels_start != -1 and line.strip() == "]":
                wheels_end = i
                break

        if wheels_start == -1 or wheels_end == -1:
            print("Error: Could not find wheels section in manifest file")
            return False

        # Create the new wheels entries
        wheel_entries = []
        for file_path in downloaded_files:
            filename = os.path.basename(file_path)
            wheel_entries.append(f'  "./wheels/{filename}",\n')

        # Replace the wheel entries
        new_content = content[:wheels_start + 1] + wheel_entries + content[wheels_end:]

        # Write the updated manifest
        with open(MANIFEST_PATH, 'w') as f:
            f.writelines(new_content)

        print(f"Successfully updated manifest with {len(downloaded_files)} wheel files")
        return True
    except Exception as e:
        print(f"Error updating manifest: {e}")
        return False


def download_wheels(test_pypi=False, specific_version=None, py_version='3.11'):
    """Download Python wheel files for the package.

    Args:
        test_pypi: Whether to download from Test PyPI
        specific_version: A specific version to download instead of the latest
        py_version: Python version to download wheels for (e.g., '3.11', '3.9-3.11')
    """
    source = "Test PyPI" if test_pypi else "PyPI"
    package_info = get_package_info(test_pypi)

    # Get the releases information
    releases = package_info.get('releases', {})

    if not releases:
        print(f"No releases found for {PACKAGE_NAME}")
        return

    # Determine which version to download
    if specific_version:
        if specific_version not in releases:
            print(f"Version {specific_version} not found for {PACKAGE_NAME}")
            print(f"Available versions: {', '.join(sorted(releases.keys()))}")
            return
        version_to_download = specific_version
        print(f"Using specified version: {version_to_download}")
    else:
        # Find the latest version
        latest_version = package_info.get('info', {}).get('version')
        if not latest_version:
            # If info.version is not available, find the latest version manually
            versions = sorted(releases.keys(), key=lambda v: [int(x) for x in v.split('.')])
            if not versions:
                print(f"No versions found for {PACKAGE_NAME}")
                return
            latest_version = versions[-1]

        version_to_download = latest_version
        print(f"Latest version found: {version_to_download}")

    create_download_dir()

    # Track number of wheels found and downloaded
    total_wheels = 0
    downloaded_wheels = 0
    downloaded_files = []

    # Process the selected version
    files = releases.get(version_to_download, [])
    if not files:
        print(f"No files found for version {version_to_download}")
        return

    print(f"\nProcessing version: {version_to_download}")

    # Filter for wheel files
    wheels = [f for f in files if f.get('packagetype') == 'bdist_wheel']

    # Filter for Python version compatible wheels
    compatible_wheels = []
    for wheel in wheels:
        filename = wheel.get('filename')
        if not filename:
            continue

        if is_python_version_compatible(filename, py_version):
            compatible_wheels.append(wheel)

    wheels = compatible_wheels

    if not wheels:
        print(f"No Python {py_version} compatible wheel files found for version {version_to_download}")
        return

    print(f"Found {len(wheels)} Python {py_version} compatible wheel file(s) for version {version_to_download}")
    total_wheels = len(wheels)

    # Download each wheel file
    for wheel in wheels:
        url = wheel.get('url')
        filename = wheel.get('filename')

        if url and filename:
            output_path = os.path.join(DOWNLOAD_DIR, filename)
            if download_file(url, output_path):
                downloaded_wheels += 1
                downloaded_files.append(output_path)

    print(f"\nDownload summary:")
    print(f"Source: {source}")
    print(f"Version: {version_to_download}")
    print(f"Total Python compatible wheel files found: {total_wheels}")
    print(f"Successfully downloaded: {downloaded_wheels}")
    print(f"Files saved to: {DOWNLOAD_DIR}")

    # Update the manifest file with the downloaded wheel files
    if downloaded_files:
        update_manifest(downloaded_files)


if __name__ == "__main__":
    args = parse_arguments()

    # Display what we're about to do
    source = "Test PyPI" if args.test_pypi else "PyPI"
    version_msg = f"version {args.version}" if args.version else "the latest version"
    print(f"Starting download of Python {args.py_version} compatible {PACKAGE_NAME} wheel files ({version_msg}) from {source}")

    # Download the wheels
    download_wheels(test_pypi=args.test_pypi, specific_version=args.version, py_version=args.py_version)
