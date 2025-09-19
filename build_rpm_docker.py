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
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import toml


def build_rpm_with_docker():
    # Load the pyproject.toml file
    with open('pyproject.toml') as f:
        project = toml.load(f)['project']

    pkg_name = project['name']
    # Insert "python3-"" prefix that follows a common convention for Python RPMs
    rpm_name = f"python3-{pkg_name.lower()}"

    docker_cmd = [
        'docker', 'run', '--rm',
        '-v', f"{os.getcwd()}:/workspace",
        '-w', '/workspace',
        'fedora:42',
        '/bin/bash', '-c',
        f"""set -ex
            # Install All build dependencies
            dnf install -y rpm-build python3-devel python3-setuptools python3-wheel python3-build python3-toml

            # Build the wheel
            python3 -m build --wheel

            # Get the wheel file name
            WHEEL_FILE=$(ls dist/*.whl)
            if [ -z "$WHEEL_FILE" ]; then
                echo "Error: No wheel file found in dist/." >&2
                exit 1
            fi
            WHEEL_FILENAME=$(basename "$WHEEL_FILE")

            # Keep RPM version as is for sorting
            RPM_VERSION="{project['version'].replace("-dev", "~dev")}"

            # Creates the standard directory structure required by rpmbuild
            mkdir -p dist/rpmbuild/{{BUILD,RPMS,SOURCES,SPECS,SRPMS}}
            mv "$WHEEL_FILE" dist/rpmbuild/SOURCES/

            # Get the changelog date
            CHANGELOG_DATE=$(date '+%a %b %d %Y')

            # Generate spec file with correct deps
            cat > dist/rpmbuild/SPECS/{rpm_name}.spec << EOF
Name:           {rpm_name}
Version:        $RPM_VERSION
Release:        1%{{?dist}}
Summary:        {project.get('description', 'Automate open source license compliance and ensure supply chain integrity')}

License:        {project.get('license', 'AGPL-3.0-only')}
URL:            {project.get('urls', '').get('Homepage', 'https://github.com/aboutcode-org/dejacode')}
Source0:        "$WHEEL_FILENAME"

BuildArch:      noarch
BuildRequires:  python3-devel python3-setuptools python3-wheel python3-build python3-toml

%description
{project.get('description', 'Automate open source license compliance and ensure supply chain integrity')}

%prep

%install
mkdir -p %{{buildroot}}%{{python3_sitelib}}
# Use the actual filename for pip install, which %SOURCE0 resolves to
pip install --no-deps --ignore-installed --root %{{buildroot}} --prefix %{{_prefix}} %{{SOURCE0}}

%files
%{{_bindir}}/dejacode
%{{python3_sitelib}}/*

%changelog
* $CHANGELOG_DATE {project.get('authors', [{}])[0].get('name', 'nexB Inc.')} - $RPM_VERSION-1
- {project.get('urls', '').get('Changelog', 'https://github.com/aboutcode-org/dejacode/blob/main/CHANGELOG.rst')}
EOF

            # Build the RPM
            rpmbuild --define "_topdir /workspace/dist/rpmbuild" -bb dist/rpmbuild/SPECS/{rpm_name}.spec

            # Fix permissions for Windows host
            chmod -R u+rwX dist/rpmbuild
        """
    ]

    try:
        subprocess.run(docker_cmd, check=True)
        # Verify the existance of the .rpm
        rpm_file = next(Path('dist/rpmbuild/RPMS/noarch').glob('*.rpm'), None)
        if rpm_file:
            print(f"\nSuccess! RPM built: {rpm_file}")
        else:
            print("Error: RPM not found in dist/rpmbuild/RPMS/noarch/", file=sys.stderr)
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    # Check if "docker" is available
    if not shutil.which('docker'):
        print("Error: Docker not found. Please install Docker first.", file=sys.stderr)
        sys.exit(1)

    build_rpm_with_docker()
