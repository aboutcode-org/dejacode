#!/usr/bin/env python3
"""
Use Docker container to build a Debian package.
Using Docker approach to ensure a consistent and isolated build environment.

Requirement:
 - toml
 - Docker

To install the required Python packages, run:

    pip install toml

To install Docker, follow the instructions at:
    https://docs.docker.com/get-docker/

To run the script:

    python build_deb_docker.py

This script will generate the Debian package files and the python wheel and
place them in the dist/debian/ directory.

Once the debian package is generated, one can install it using:

    sudo apt install ./<package>.deb

Note: The ./ is important - it tells apt to install from a local file
rather than searching repositories.
Replace the above path with the actual path to the generated debian file.

Run the binary directly

    dejacode
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

    # Get all dependencies
    dependencies = project.get("dependencies", [])

    filtered_dependencies = [
        dep
        for dep in dependencies
        if "django-rest-hooks" not in dep and "django_notifications_patched" not in dep
    ]

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.getcwd()}:/workspace",
        "-w",
        "/workspace",
        "ubuntu:24.04",
        "/bin/bash",
        "-c",
        f"""set -ex
            # Install build dependencies
            apt-get update
            apt-get install -y debhelper dh-python devscripts build-essential \
                libsasl2-dev libldap2-dev libssl-dev libpq-dev

            # Install Python 3.13 from deadsnakes PPA
            apt-get install -y software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa
            apt-get update
            apt-get install -y python3.13 python3.13-dev python3.13-venv

            # Create and activate virtual environment with Python 3.13 using --copies
            python3.13 -m venv /opt/{deb_name} --copies
            . /opt/{deb_name}/bin/activate

            # Upgrade pip to latest version and ensure setuptools is available
            pip install --upgrade pip setuptools wheel

            # Clean previous build artifacts
            rm -rf build/

            # Install non-PyPI dependencies
            pip install https://github.com/aboutcode-org/django-rest-hooks/releases/download/1.6.1/django_rest_hooks-1.6.1-py2.py3-none-any.whl
            pip install https://github.com/dejacode/django-notifications-patched/archive/refs/tags/2.0.0.tar.gz

            # Install dependencies directly
            {" && ".join([f'pip install "{dep}"' for dep in filtered_dependencies])}

            # Install build tool
            pip install build

            # Build the wheel
            python3.13 -m build --wheel

            # Install the package and all remaining dependencies
            WHEEL_FILE=$(ls dist/*.whl)

            # Install the main package
            pip install "$WHEEL_FILE"

            # Copy source code to /opt/{deb_name}/src
            mkdir -p /opt/{deb_name}/src
            cp -r /workspace/* /opt/{deb_name}/src/ 2>/dev/null || true
            rm -rf /opt/{deb_name}/src/dist /opt/{deb_name}/src/build 2>/dev/null || true

            # Fix shebangs in the virtual environment to use absolute paths
            for script in /opt/{deb_name}/bin/*; do
                if [ -f "$script" ] && head -1 "$script" | grep -q "^#!"; then
                    # Use sed to safely replace only the first line with absolute path
                    sed -i '1s|.*|#!/opt/{deb_name}/bin/python3|' "$script"
                fi
            done

            # Remove pip and wheel to reduce package size
            rm -f /opt/{deb_name}/bin/pip* /opt/{deb_name}/bin/wheel

            # Ensure all scripts are executable
            chmod -R 755 /opt/{deb_name}/bin/

            # Create wrapper script (like in RPM) instead of direct symlink
            cat > /opt/{deb_name}/bin/dejacode-wrapper << 'WRAPPER_EOF'
#!/bin/bash
export PYTHONPATH="/opt/{deb_name}/src:/opt/{deb_name}/lib/python3.13/site-packages"
cd "/opt/{deb_name}/src"
exec "/opt/{deb_name}/bin/dejacode" "$@"
WRAPPER_EOF
            chmod 755 /opt/{deb_name}/bin/dejacode-wrapper

            # Create temporary directory for package building
            TEMP_DIR=$(mktemp -d)
            PKG_DIR="$TEMP_DIR/{deb_name}-{deb_version}"
            mkdir -p "$PKG_DIR"

            # Copy the installed package files
            mkdir -p "$PKG_DIR/opt/"
            cp -r /opt/{deb_name} "$PKG_DIR/opt/"

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
Depends: python3.13, git, libldap2 | libldap-2.5-0, libsasl2-2, libssl3 | libssl3t64, libpq5
Section: python
Priority: optional
Homepage: {project.get("urls", "").get("Homepage", "https://github.com/aboutcode-org/dejacode")}
EOF

            # Create postinst script to setup symlinks
            cat > "$PKG_DIR/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
# Create symlinks for binaries - use the wrapper script
if [ -f "/opt/{deb_name}/bin/dejacode-wrapper" ]; then
    ln -sf "/opt/{deb_name}/bin/dejacode-wrapper" "/usr/local/bin/dejacode"
fi

# Ensure proper permissions
chmod -R 755 /opt/{deb_name}/bin/
POSTINST
            chmod 755 "$PKG_DIR/DEBIAN/postinst"

            # Create prerm script to clean up symlinks
            cat > "$PKG_DIR/DEBIAN/prerm" << 'PRERM'
#!/bin/bash
# Remove symlinks
rm -f "/usr/local/bin/dejacode"
PRERM
            chmod 755 "$PKG_DIR/DEBIAN/prerm"

            # Build the .deb package
            mkdir -p dist/debian
            dpkg-deb --build "$PKG_DIR" "dist/debian/{deb_name}_{deb_version}_all.deb"

            # Move wheel to dist/debian/
            mv dist/*.whl dist/debian/

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
