#!/usr/bin/env python3
"""
Use Docker container to build a Debian package.
Using Docker approach to ensure a consistent and isolated build environment.

Requirement: The `toml` Python package

    pip install toml

To run the script:

    python build_deb_docker.py

This script will generate the Debian package files and place them in the
dist/debian/ directory.

Once the debian package is generated, you can install it using:

    sudo apt install ./<package>.deb

Note: The ./ is important - it tells apt to install from a local file
rather than searching repositories.
Replace the above path with the actual path to the generated debian file.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import toml


def build_deb_with_docker():
    # Load the pyproject.toml file
    with open("pyproject.toml") as f:
        project = toml.load(f)["project"]

    pkg_name = project["name"]
    # Insert "python3-"" prefix that follows a common convention
    deb_name = f"python3-{pkg_name.lower()}"

    # Debian version conventions replace hyphens with tildes
    deb_version = project["version"].replace("-dev", "~dev")

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.getcwd()}:/workspace",
        "-w",
        "/workspace",
        "ubuntu:22.04",
        "/bin/bash",
        "-c",
        f"""set -ex
            # Install build dependencies
            apt-get update
            apt-get install -y python3-dev python3-pip python3-venv debhelper dh-python devscripts

            # Install build tool
            pip install build

            # Build the wheel
            python3 -m build --wheel

            # Move wheel to dist/debian/
            mkdir -p dist/debian
            mv dist/*.whl dist/debian/

            # Get the wheel file name
            WHEEL_FILE=$(ls dist/debian/*.whl)
            if [ -z "$WHEEL_FILE" ]; then
                echo "Error: No wheel file found in dist/debian/." >&2
                exit 1
            fi

            # Create temporary directory for package building
            TEMP_DIR=$(mktemp -d)
            PKG_DIR="$TEMP_DIR/{deb_name}-{deb_version}"
            mkdir -p "$PKG_DIR"

            # Extract wheel contents to package directory
            unzip "$WHEEL_FILE" -d "$PKG_DIR"

            # Create DEBIAN control file
            mkdir -p "$PKG_DIR/DEBIAN"
            cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: {deb_name}
Version: {deb_version}
Architecture: all
Maintainer: {project.get("authors", [{}])[0].get("name", "nexB Inc.")}
Description: {
            project.get(
                "description",
                "Automate open source license compliance andensure supply chain integrity",
            )
        }
Depends: python3
Section: python
Priority: optional
Homepage: {project.get("urls", "").get("Homepage", "https://github.com/aboutcode-org/dejacode")}
EOF

            # Build the .deb package
            dpkg-deb --build "$PKG_DIR" dist/debian/

            # Clean up
            rm -rf "$TEMP_DIR"

            # Fix permissions for Windows host
            chmod -R u+rwX dist/debian/
        """,
    ]

    try:
        subprocess.run(docker_cmd, check=True, shell=False)  # noqa: S603
        # Verify the existence of the .deb
        deb_file = next(Path("dist/debian").glob("*.deb"), None)
        if deb_file:
            print(f"\nSuccess! Debian package built: {deb_file}")
        else:
            print("Error: Debian package not found in dist/debian/", file=sys.stderr)
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Check if "docker" is available
    if not shutil.which("docker"):
        print("Error: Docker not found. Please install Docker first.", file=sys.stderr)
        sys.exit(1)

    # Get the directory where the current script is located (which is located in etc/scripts)
    script_dir = Path(__file__).parent.resolve()
    # Go up two levels from etc/scripts/
    project_root = script_dir.parent.parent
    os.chdir(project_root)
    build_deb_with_docker()
