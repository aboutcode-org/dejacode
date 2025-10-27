#!/usr/bin/env python3
"""
Use Docker container to build an RPM.
Using Docker approach to ensure a consistent and isolated build environment.

Requirement: The `toml` Python package

    pip install toml

To run the script:

    python build_rpm_docker.py

This script will generate the RPM package files and place them in the
dist/rpmbuild/ directory.

Once the RPM package is generated, you can install it using:

    sudo rpm -i /path/to/<dejacode>.rpm
    OR
    sudo dnf install /path/to/<dejacode>.rpm
    OR
    sudo yum install /path/to/<dejacode>.rpm

Replace the above path with the actual path to the generated RPM file.
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

    # Exclude packages that will be installed from GitHub URLs
    excluded_packages = {"django-rest-hooks", "django_notifications_patched"}

    filtered_dependencies = [
        dep for dep in dependencies if not any(excluded in dep for excluded in excluded_packages)
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
# Install All build dependencies including development tools
dnf install -y rpm-build python3-devel python3-setuptools python3-wheel \
    python3-build python3-pip python3-virtualenv curl gcc openldap-devel

# Clean up build directories to prevent recursive copying
rm -rf build

# Build the wheel
python3 -m build --wheel

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

# Create source tarball with actual name
tar czf dist/rpmbuild/SOURCES/{rpm_name}-{rpm_version}.tar.gz \\
    --transform "s,^,/{rpm_name}-{rpm_version}/," \\
    -C /workspace \\
    --exclude build --exclude=.git --exclude=dist --exclude=*.pyc --exclude=__pycache__ .

# Generate spec file with virtualenv approach - using actual values instead of variables
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

BuildArch:      noarch
BuildRequires:  python3-devel python3-virtualenv gcc openldap-devel
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
# Create directories
mkdir -p %{{buildroot}}/opt/%{{name}}/venv
mkdir -p %{{buildroot}}/usr/bin

# Create virtual environment in a temporary location first
mkdir -p /tmp/venv_build
python3 -m venv /tmp/venv_build

# Upgrade pip in the temporary virtual environment
/tmp/venv_build/bin/pip install --upgrade pip

# funcparserlib Patch/Install
cd /tmp
curl -L -o funcparserlib-0.3.6.tar.gz https://files.pythonhosted.org/packages/source/f/funcparserlib/funcparserlib-0.3.6.tar.gz
tar -xzf funcparserlib-0.3.6.tar.gz
cd funcparserlib-0.3.6

# rewrite setup.py to remove the "use_2to3" as this is not suported in Python3
cat > setup.py << 'SETUP_EOF'
from setuptools import setup

setup(
    name='funcparserlib',
    version='0.3.6',
    packages=['funcparserlib', 'funcparserlib.tests'],
    author='Andrey Vlasovskikh',
    author_email='andrey.vlasovskikh@gmail.com',
    description='Recursive descent parsing library based on functional '
        'combinators',
    license='MIT',
    url='http://code.google.com/p/funcparserlib/',
)
SETUP_EOF

# Install the patched funcparserlib
/tmp/venv_build/bin/pip install .

# Clean up
cd /tmp
rm -rf funcparserlib-0.3.6 funcparserlib-0.3.6.tar.gz

# Install all other dependencies including the main package
cd %{{_sourcedir}}
/tmp/venv_build/bin/pip install -r requirements.txt

# Install non-PyPI dependencies
/tmp/venv_build/bin/pip install \\
    https://github.com/aboutcode-org/django-rest-hooks/releases/download/1.6.1/django_rest_hooks-1.6.1-py2.py3-none-any.whl

/tmp/venv_build/bin/pip install \\
    https://github.com/dejacode/django-notifications-patched/archive/refs/tags/2.0.0.tar.gz

# Install the main package from the wheel
/tmp/venv_build/bin/pip install --no-deps $WHEEL_FILENAME

# Copy the completed virtual environment to the final location
cp -r /tmp/venv_build/* %{{buildroot}}/opt/%{{name}}/venv/

# Clean up temporary virtual environment
rm -rf /tmp/venv_build

# Doing clean up to prevent the "Arch dependent binaries in noarch package" error.
# Remove arch-dependent shared object files (*.so)
find %{{buildroot}}/opt/%{{name}}/venv -name "*.so*" -type f -delete

# Remove any other potential binary files
find %{{buildroot}}/opt/%{{name}}/venv -type f -exec file {{}} \\; | grep -i \
    "executable" | cut -d: -f1 | xargs -r rm -f

# Create wrapper script for dejacode command
cat > %{{buildroot}}/usr/bin/dejacode << 'WRAPPER_EOF'
#!/bin/sh
export PYTHONPATH="/opt/{rpm_name}/venv/lib/python3.13/site-packages"
exec /usr/bin/python3 -m dejacode "\\$@"
WRAPPER_EOF
chmod 755 %{{buildroot}}/usr/bin/dejacode

# Clean up any remaining build artifacts
find %{{buildroot}}/opt/%{{name}}/venv -name "*.pyc" -delete
find %{{buildroot}}/opt/%{{name}}/venv -name "__pycache__" -type d \
    -exec rm -rf {{}} + 2>/dev/null || true
find %{{buildroot}}/opt/%{{name}}/venv -path "*/pip/_vendor/distlib/*.tmp" \
    -delete 2>/dev/null || true

%files
%dir /opt/%{{name}}
/opt/%{{name}}/venv
/usr/bin/dejacode

%changelog
* $CHANGELOG_DATE {project.get("authors", [{}])[0].get("name", "nexB Inc.")} - {rpm_version}-1
- {
            project.get("urls", "").get(
                "Changelog", "https://github.com/aboutcode-org/dejacode/blob/main/CHANGELOG.rst"
            )
        }
EOF

# Build the RPM
cd dist/rpmbuild && rpmbuild --define "_topdir $(pwd)" -bb SPECS/{rpm_name}.spec

# Fix permissions for Windows host
chmod -R u+rwX /workspace/dist/rpmbuild
""",
    ]

    try:
        subprocess.run(docker_cmd, check=True, shell=False)  # noqa: S603
        # Verify the existence of the .rpm
        rpm_file = next(Path("dist/rpmbuild/RPMS/noarch").glob("*.rpm"), None)
        if rpm_file:
            print(f"\nSuccess! RPM built: {rpm_file}")
        else:
            print("Error: RPM not found in dist/rpmbuild/RPMS/noarch/", file=sys.stderr)
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
