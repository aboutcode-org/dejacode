#!/usr/bin/env python3
"""
Use Docker container to build an RPM.
Using Docker approach to ensure a consistent and isolated build environment.

Requirement:
 - toml
 - Docker

To install the required Python packages, run:

    pip install toml

To install Docker, follow the instructions at:
    https://docs.docker.com/get-docker/

To run the script:

    python build_rpm_docker.py

This script will generate the RPM package files and place them in the
dist/rpmbuild/ directory.

Once the RPM package is generated, one can install it using:

    sudo rpm -i /path/to/<dejacode>.rpm
    OR
    sudo dnf install /path/to/<dejacode>.rpm
    OR
    sudo yum install /path/to/<dejacode>.rpm

Replace the above path with the actual path to the generated RPM file.

Run the binary directly

    dejacode
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import toml


def build_rpm_with_docker():
    # Load the pyproject.toml file
    with open("pyproject.toml") as f:
        project = toml.load(f)["project"]

    pkg_name = project["name"]
    # Insert "python3-"" prefix that follows a common convention for Python RPMs
    rpm_name = f"python3-{pkg_name.lower()}"
    rpm_version = project["version"].replace("-dev", "~dev")

    # Generate requirements for RPM - exclude packages installed from GitHub
    dependencies = project["dependencies"]

    filtered_dependencies = [
        dep
        for dep in dependencies
        if "django-rest-hooks" not in dep and "django-notifications-patched" not in dep
    ]

    # Create a requirements.txt content for installation
    requirements_content = "\n".join(filtered_dependencies)

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.getcwd()}:/workspace",
        "-w",
        "/workspace",
        "fedora:42",
        "/bin/bash",
        "-c",
        f"""set -ex
# Install build dependencies
dnf install -y rpm-build python3.13-devel python3.13-setuptools python3.13-wheel \\
    python3.13-build python3.13-pip python3.13-virtualenv curl gcc openldap-devel git

# Clean up and build wheel
rm -rf build dist
python3.13 -m build --wheel

# Get the wheel file name
WHEEL_FILE=$(ls dist/*.whl)
if [ -z "$WHEEL_FILE" ]; then
    echo "Error: No wheel file found in dist/." >&2
    exit 1
fi
WHEEL_FILENAME=$(basename "$WHEEL_FILE")

# Creates the standard directory structure required by rpmbuild
mkdir -p dist/rpmbuild/{{BUILD,RPMS,SOURCES,SPECS,SRPMS}}
mv "$WHEEL_FILE" dist/rpmbuild/SOURCES/

# Create requirements.txt in SOURCES
cat > dist/rpmbuild/SOURCES/requirements.txt << 'REQ_EOF'
{requirements_content}
REQ_EOF

# Get the changelog date
CHANGELOG_DATE=$(date '+%a %b %d %Y')

# Create source tarball
tar czf dist/rpmbuild/SOURCES/{rpm_name}-{rpm_version}.tar.gz \\
    --transform "s,^,/{rpm_name}-{rpm_version}/," \\
    -C /workspace \\
    --exclude build --exclude=.git --exclude=dist --exclude=*.pyc --exclude=__pycache__ .

# Generate spec file
cat > dist/rpmbuild/SPECS/{rpm_name}.spec << EOF
Name:           {rpm_name}
Version:        {rpm_version}
Release:        1%{{?dist}}
Summary:        {
            project.get(
                "description",
                "Automate open source license compliance and ensure supply chain integrity",
            )
        }

License:        {project.get("license", "AGPL-3.0-only")}
URL:            {
            project.get("urls", "").get("Homepage", "https://github.com/aboutcode-org/dejacode")
        }
Source0:        {rpm_name}-{rpm_version}.tar.gz
Source1:        requirements.txt
Source2:        $WHEEL_FILENAME

BuildArch:      x86_64
BuildRequires:  python3.13-devel python3.13-virtualenv gcc openldap-devel git

# Runtime dependencies
Requires:       git
Requires:       python3.13
Requires:       postgresql
Requires:       postgresql-devel
Requires:       openldap

# Disable automatic debug package generation and file checking
%global debug_package %{{nil}}
%global __check_files %{{nil}}
%global _enable_debug_package 0

# Only disable python bytecompilation which breaks virtualenvs
%global __brp_python_bytecompile %{{nil}}

# Keep shebang mangling disabled for virtualenv
%global __os_install_post %(echo '%{{__os_install_post}}' | \
    sed -e 's!/usr/lib/rpm/redhat/brp-mangle-shebangs!!g')
%global __brp_mangle_shebangs %{{nil}}

AutoReqProv:    no

%description
{
            project.get(
                "description",
                "Automate open source license compliance and ensure supply chain integrity",
            )
        }

%prep
%setup -q

%build

%install
rm -rf %{{buildroot}}
# Create directories
mkdir -p %{{buildroot}}/opt/%{{name}}/venv
mkdir -p %{{buildroot}}/usr/bin
mkdir -p %{{buildroot}}/opt/%{{name}}/src

# Create virtual environment in a temporary location first
mkdir -p /tmp/venv_build
python3.13 -m venv /tmp/venv_build --copies

cd %{{_sourcedir}}
/tmp/venv_build/bin/python -m pip install --upgrade pip

# Install system dependencies for psycopg
dnf install -y postgresql-devel

# Install non-PyPI dependencies
/tmp/venv_build/bin/python -m pip install \\
    https://github.com/aboutcode-org/django-rest-hooks/releases/download/1.6.1/django_rest_hooks-1.6.1-py2.py3-none-any.whl
/tmp/venv_build/bin/python -m pip install \\
    https://github.com/dejacode/django-notifications-patched/archive/refs/tags/2.0.0.tar.gz

# Install the main package
/tmp/venv_build/bin/python -m pip install -r requirements.txt

# Install psycopg2-binary for compatibility
/tmp/venv_build/bin/python -m pip install psycopg2-binary

# Install dejacode wheel
/tmp/venv_build/bin/python -m pip install %{{_sourcedir}}/$WHEEL_FILENAME

# Extract source code for tests
cd %{{_sourcedir}}
tar xzf {rpm_name}-{rpm_version}.tar.gz
cp -r {rpm_name}-{rpm_version}/* %{{buildroot}}/opt/%{{name}}/src/

# Clean up temporary virtualenv
find /tmp/venv_build -name "*.pyc" -delete
find /tmp/venv_build -name "__pycache__" -type d -exec rm -rf {{}} + 2>/dev/null || true

# Copy the completed virtual environment to the final location
cp -r /tmp/venv_build/* %{{buildroot}}/opt/%{{name}}/venv/

# Clean up temporary virtual environment
rm -rf /tmp/venv_build

# Fix shebang
for script in %{{buildroot}}/opt/%{{name}}/venv/bin/*; do
    if [ -f "\\$script" ] && head -1 "\\$script" | grep -q "^#!"; then
        # Use sed to safely replace only the first line
        sed -i '1s|.*|#!/opt/%{{name}}/venv/bin/python3|' "\\$script"
    fi
done

# Remove ONLY pip and wheel binaries
rm -f %{{buildroot}}/opt/%{{name}}/venv/bin/pip*
rm -f %{{buildroot}}/opt/%{{name}}/venv/bin/wheel

# Ensure executables have proper permissions
find %{{buildroot}}/opt/%{{name}}/venv/bin -type f -exec chmod 755 {{}} \\;

# Create wrapper script with PYTHONPATH for tests
cat > %{{buildroot}}/usr/bin/dejacode << 'WRAPPER_EOF'
#!/bin/sh
export PYTHONPATH="/opt/%{{name}}/src:/opt/%{{name}}/venv/lib/python3.13/site-packages"
cd "/opt/%{{name}}/src"
/opt/%{{name}}/venv/bin/dejacode "\\$@"
WRAPPER_EOF
chmod 755 %{{buildroot}}/usr/bin/dejacode

%files
%defattr(-,root,root,-)
%dir /opt/%{{name}}
/opt/%{{name}}/venv/
/opt/%{{name}}/src/
/usr/bin/dejacode

%changelog
* $CHANGELOG_DATE {project.get("authors", [{}])[0].get("name", "nexB Inc.")} - {rpm_version}-1
- {
            project.get("urls", "").get(
                "Changelog", "https://github.com/aboutcode-org/dejacode/blob/main/CHANGELOG.rst"
            )
        }
EOF

# Build RPM with only specific BRP processing disabled
cd dist/rpmbuild && rpmbuild \\
    --define "_topdir $(pwd)" \\
    --define "__check_files /bin/true" \\
    --define "__brp_python_bytecompile /bin/true" \\
    -bb SPECS/{rpm_name}.spec


# Fix permissions for Windows host
chmod -R u+rwX /workspace/dist/rpmbuild
""",
    ]

    try:
        subprocess.run(docker_cmd, check=True, shell=False)  # noqa: S603
        # Verify the existence of the .rpm
        rpm_file = next(Path("dist/rpmbuild/RPMS/x86_64").glob("*.rpm"), None)
        if rpm_file:
            print(f"\nSuccess! RPM built: {rpm_file}")
        else:
            print("Error: RPM not found in dist/rpmbuild/RPMS/x86_64/", file=sys.stderr)
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
    build_rpm_with_docker()
