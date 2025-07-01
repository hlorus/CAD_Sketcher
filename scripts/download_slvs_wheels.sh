#!/bin/bash
#
# Download Python 3.11 compatible wheel files for the slvs package
# and update the manifest file with the downloaded wheel files
#
# Usage:
#   ./download_slvs_wheels.sh [OPTIONS]
#
# Options:
#   --test-pypi      Download from Test PyPI instead of PyPI
#   --version VERSION Download a specific version instead of the latest
#
# Examples:
# Download the latest version from PyPI (default)
# ./scripts/download_slvs_wheels.sh
# Download from Test PyPI instead
# ./scripts/download_slvs_wheels.sh --test-pypi
# Download a specific version from PyPI
# ./scripts/download_slvs_wheels.sh --version 3.1.0
# Download a specific version from Test PyPI
# ./scripts/download_slvs_wheels.sh --test-pypi --version 3.1.0


# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Parse command line arguments
PYPI_SOURCE="PyPI"
VERSION_MSG="the latest version"
PYTHON_ARGS=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --test-pypi)
      PYPI_SOURCE="Test PyPI"
      PYTHON_ARGS="$PYTHON_ARGS --test-pypi"
      shift
      ;;
    --version)
      VERSION="$2"
      VERSION_MSG="version $VERSION"
      PYTHON_ARGS="$PYTHON_ARGS --version $VERSION"
      shift 2
      ;;
    --version=*)
      VERSION="${1#*=}"
      VERSION_MSG="version $VERSION"
      PYTHON_ARGS="$PYTHON_ARGS --version $VERSION"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--test-pypi] [--version VERSION]"
      exit 1
      ;;
  esac
done

# Print a message to the console
echo "Downloading Python 3.11 compatible slvs wheel files (${VERSION_MSG}) from ${PYPI_SOURCE}..."
echo "The manifest file will be updated with the downloaded wheel files."

# Run the Python script with the parsed arguments
python3 "${SCRIPT_DIR}/download_slvs_wheels.py" $PYTHON_ARGS

# Check if the script executed successfully
if [ $? -eq 0 ]; then
    echo "Download complete and manifest updated!"
else
    echo "Error: Download failed!"
    exit 1
fi
