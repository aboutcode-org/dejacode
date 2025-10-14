#!/usr/bin/env python3
"""
Use Docker container to run nix-build.
Using Docker approach to ensure a consistent and isolated build environment.

Requirement: `toml` and `requests` Python packages and Docker installed.

    pip install toml requests

To run the script:

    python build_nix_docker.py

or

    python build_nix_docker.py --generate

    The --generate flag is optional and can be used to generate the
    default.nix file if needed.

This script will run nix-build and place the built results in the
dist/nix/ directory, it will then run nix-collect-garbage for cleanup.
"""

import argparse
import os
import requests
import shutil
import subprocess
import sys
from pathlib import Path


def read_pyproject_toml():
    """
    Read the pyproject.toml file to extract project metadata.
    """
    import toml

    pyproject_path = Path('pyproject.toml')
    if not pyproject_path.exists():
        print("Error: pyproject.toml not found in current directory", file=sys.stderr)
        sys.exit(1)

    with pyproject_path.open('r') as f:
        pyproject_data = toml.load(f)

    return pyproject_data

def extract_project_meta(pyproject_data):
    """
    Extract project metadata from pyproject.toml data.
    """
    project_data = pyproject_data['project']
    name = project_data.get('name')
    version = project_data.get('version')
    description = project_data.get('description')
    authors = project_data.get('authors')
    author_names = [author.get('name', '') for author in authors if 'name' in author]
    author_str = ', '.join(author_names)

    meta_dict = {
        'name': name,
        'version': version,
        'description': description,
        'author': author_str
    }

    return meta_dict


def extract_project_dependencies(pyproject_data):
    """
    Extract project dependencies from pyproject.toml data.
    """
    project_data = pyproject_data['project']
    dependencies = project_data.get('dependencies', [])
    optional_dependencies = project_data.get('optional-dependencies', {})
    dev_optional_deps = optional_dependencies.get('dev', [])
    all_dep = dependencies + dev_optional_deps
    dependencies_list = []

    for dep in all_dep:
        name_version = dep.split('==')
        name = name_version[0]
        version = name_version[1]
        tmp_dict = {}
        tmp_dict['name'] = name
        tmp_dict['version'] = version
        dependencies_list.append(tmp_dict)

    assert len(all_dep) == len(dependencies_list), "Dependency extraction mismatch"
    return dependencies_list


def create_defualt_nix(dependencies_list, meta_dict):
    """
    Create a default.nix
    """
    nix_content = """
{
  pkgs ? import <nixpkgs> { },
}:

let
  python = pkgs.python313;

  # Helper function to override a package to disable tests
  disableAllTests =
    package: extraAttrs:
    package.overrideAttrs (
      old:
      {
        doCheck = false;
        doInstallCheck = false;
        doPytestCheck = false;
        pythonImportsCheck = [];
        checkPhase = "echo 'Tests disabled'";
        installCheckPhase = "echo 'Install checks disabled'";
        pytestCheckPhase = "echo 'Pytest checks disabled'";
        __intentionallyOverridingVersion = old.__intentionallyOverridingVersion or false;
      }
      // extraAttrs
    );

  pythonOverlay = self: super: {
"""
    need_review_packages_list = []
    deps_size = len(dependencies_list)
    for idx, dep in enumerate(dependencies_list):
        print("Processing {}/{}: {}".format(idx + 1, deps_size, dep['name']))
        name = dep['name']
        version = dep['version']
        # Handle 'django_notifications_patched','django-rest-hooks' and 'funcparserlib' separately
        if not name == 'django-rest-hooks' and not name == 'django_notifications_patched' and not name == 'funcparserlib':
            url = "https://pypi.org/pypi/{name}/{version}/json".format(name=name, version=version)
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()

                url_section = data.get("urls", [])
                build_from_src = True
                package_added = False
                for component in url_section:
                    if component.get("packagetype") == "bdist_wheel":
                        whl_url = component.get("url")
                        whl_sha256 = get_sha256_hash(whl_url)
                        nix_content += '    ' + name + ' = python.pkgs.buildPythonPackage {\n'
                        nix_content += '        pname = "' + name + '";\n'
                        nix_content += '        version = "' + version + '";\n'
                        nix_content += '        format = "wheel";\n'
                        nix_content += '        src = pkgs.fetchurl {\n'
                        nix_content += '          url = "' + whl_url + '";\n'
                        nix_content += '          sha256 = "' + whl_sha256 + '";\n'
                        nix_content += '        };\n'
                        nix_content += '    };\n'
                        build_from_src = False
                        package_added = True
                        break

                if build_from_src:
                    for component in url_section:
                        if component.get("packagetype") == "sdist":
                            sdist_url = component.get("url")
                            sdist_sha256 = get_sha256_hash(sdist_url)
                            nix_content += '    ' + name + ' = disableAllTests super.' + name + ' {\n'
                            nix_content += '        pname = "' + name + '";\n'
                            nix_content += '        version = "' + version + '";\n'
                            nix_content += '        __intentionallyOverridingVersion = true;\n'
                            nix_content += '        src = pkgs.fetchurl {\n'
                            nix_content += '          url = "' + sdist_url + '";\n'
                            nix_content += '          sha256 = "' + sdist_sha256 + '";\n'
                            nix_content += '        };\n'
                            nix_content += '    };\n'
                            package_added = True
                            break
                if not package_added:
                    need_review_packages_list.append(dep)
            except requests.exceptions.RequestException as e:
                need_review_packages_list.append(dep)
        else:
            if name == 'django-rest-hooks' and version == '1.6.1':
                nix_content += '    ' + name + ' = python.pkgs.buildPythonPackage {\n'
                nix_content += '        pname = "django-rest-hooks";\n'
                nix_content += '        version = "1.6.1";\n'
                nix_content += '        format = "wheel";\n'
                nix_content += '        src = pkgs.fetchurl {\n'
                nix_content += '          url = "https://github.com/aboutcode-org/django-rest-hooks/releases/download/1.6.1/django_rest_hooks-1.6.1-py2.py3-none-any.whl";\n'
                nix_content += '          sha256 = "1byakq3ghpqhm0mjjkh8v5y6g3wlnri2vvfifyi9ky36l12vqx74";\n'
                nix_content += '        };\n'
                nix_content += '    };\n'
            elif name == 'django_notifications_patched' and version == '2.0.0':
                nix_content += '    ' + name + ' = self.buildPythonPackage rec {\n'
                nix_content += '        pname = "django_notifications_patched";\n'
                nix_content += '        version = "2.0.0";\n'
                nix_content += '        format = "setuptools";\n'
                nix_content += '        doCheck = false;\n'
                nix_content += '        src = pkgs.fetchFromGitHub {\n'
                nix_content += '           owner = "dejacode";\n'
                nix_content += '           repo = "django-notifications-patched";\n'
                nix_content += '           rev = "2.0.0";\n'
                nix_content += '           url = "https://github.com/dejacode/django-notifications-patched/archive/refs/tags/2.0.0.tar.gz";\n'
                nix_content += '           sha256 = "sha256-RDAp2PKWa2xA5ge25VqkmRm8HCYVS4/fq2xKc80LDX8=";\n'
                nix_content += '        };\n'
                nix_content += '    };\n'
            elif name == 'funcparserlib' and version == '0.3.6':
                nix_content += '    ' + name + ' = self.buildPythonPackage rec {\n'
                nix_content += '        pname = "funcparserlib";\n'
                nix_content += '        version = "0.3.6";\n'
                nix_content += '        format = "setuptools";\n'
                nix_content += '        doCheck = false;\n'
                nix_content += '        src = pkgs.fetchurl {\n'
                nix_content += '          url = "https://files.pythonhosted.org/packages/cb/f7/b4a59c3ccf67c0082546eaeb454da1a6610e924d2e7a2a21f337ecae7b40/funcparserlib-0.3.6.tar.gz";\n'
                nix_content += '           sha256 = "07f9cgjr3h4j2m67fhwapn8fja87vazl58zsj4yppf9y3an2x6dp";\n'
                nix_content += '        };\n\n'
                # Original setpy.py: https://github.com/vlasovskikh/funcparserlib/blob/0.3.6/setup.py
                # funcparserlib version 0.3.6 uses use_2to3 which is no longer supported in modern setuptools.
                # Remove the "use_2to3" from the setup.py
                nix_content += "    postPatch = ''\n"
                nix_content += '        cat > setup.py << EOF\n'
                nix_content += '        # -*- coding: utf-8 -*-\n'
                nix_content += '        from setuptools import setup\n'
                nix_content += '        setup(\n'
                nix_content += '            name="funcparserlib",\n'
                nix_content += '            version="0.3.6",\n'
                nix_content += '            packages=["funcparserlib", "funcparserlib.tests"],\n'
                nix_content += '            author="Andrey Vlasovskikh",\n'
                nix_content += '            description="Recursive descent parsing library based on functional combinators",\n'
                nix_content += '            license="MIT",\n'
                nix_content += '            url="http://code.google.com/p/funcparserlib/",\n'
                nix_content += '        )\n'
                nix_content += '        EOF\n'
                nix_content += "    '';\n"
                nix_content += '    propagatedBuildInputs = with self; [];\n'
                nix_content += '    checkPhase = "echo \'Tests disabled for funcparserlib\'";\n'
                nix_content += '    };\n'
            else:
                need_review_packages_list.append(dep)
    nix_content += """
  };
  pythonWithOverlay = python.override {
      packageOverrides =
      self: super:
      let
          # Override buildPythonPackage to disable tests for ALL packages
          base = {
            buildPythonPackage =
              attrs:
              super.buildPythonPackage (
              attrs
              // {
                doCheck = false;
                doInstallCheck = false;
                doPytestCheck = false;
                pythonImportsCheck = [];
                }
              );
          };

          # Apply custom package overrides
          custom = pythonOverlay self super;
      in
        base // custom;
  };

  pythonApp = pythonWithOverlay.pkgs.buildPythonApplication {
"""

    nix_content += '    name = "' + meta_dict['name'] + '";\n'
    nix_content += '    version = "' + meta_dict['version'] + '";\n'

    nix_content += """
    src = ./.;
    doCheck = false;
    doInstallCheck = false;
    doPytestCheck = false;
    pythonImportsCheck = [];

    format = "pyproject";

    nativeBuildInputs = with pythonWithOverlay.pkgs; [
      setuptools
      wheel
      pip
    ];

    propagatedBuildInputs = with pythonWithOverlay.pkgs; [
"""

    for dep in dependencies_list:
        name = dep['name']
        nix_content += '      ' + name + '\n'

    nix_content += """
    ];

    meta = with pkgs.lib; {
      description = "Automate open source license compliance and ensure supply chain integrity";
      license = "AGPL-3.0-only";
      maintainers = ["AboutCode.org"];
      platforms = platforms.linux;
    };
  };

in
{
  # Default output is the Python application
  app = pythonApp;

  # Default to the application
  default = pythonApp;
}
"""
    return nix_content, need_review_packages_list


def get_sha256_hash(url):
    """
    Get SHA256 hash of a file using nix-prefetch-url.
    """
    try:
        result = subprocess.run(
            ['nix-prefetch-url', url],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running nix-prefetch-url for {url}: {e}")
        return None
    except FileNotFoundError:
        print("Error: nix-prefetch-url command not found. Make sure nix is installed.")
        return None


def cleanup_nix_store():
    """
    Remove the nix-store volume to ensure clean state
    """
    try:
        subprocess.run(['docker', 'volume', 'rm', 'nix-store'],
                      check=True, capture_output=True)
        print("Cleaned up nix-store volume.")
    except subprocess.CalledProcessError as e:
        # Volume might not exist, which is fine
        if "no such volume" not in e.stderr.decode().lower():
            print(f"Warning: Could not remove nix-store volume: {e.stderr.decode()}")
        pass


def build_nix_with_docker():
    # Create output directory
    output_dir = Path('dist/nix')
    output_dir.mkdir(parents=True, exist_ok=True)

    docker_cmd = [
        'docker', 'run', '--rm',
        '-v', f"{os.getcwd()}:/workspace",
        '-v', 'nix-store:/nix',
        '-w', '/workspace',
        'nixos/nix',
        '/bin/sh', '-c',
        f"""set -ex
            # Update nix-channel to get latest packages
            nix-channel --update

            # Run nix-build
            nix-build default.nix -o result

            # Check if build was successful
            if [ -d result ]; then
                # Copy the build result to dist/nix/
                mkdir -p /workspace/dist/nix
                # Use nix-store to get the actual store path
                STORE_PATH=$(readlink result)
                cp -r "$STORE_PATH"/* /workspace/dist/nix/ || true

                # Also copy the symlink target directly if directory copy fails
                if [ ! "$(ls -A /workspace/dist/nix/)" ]; then
                    # If directory is empty, try to copy the store path itself
                    cp -r "$STORE_PATH" /workspace/dist/nix/store_result || true
                fi

                # Remove the result symlink
                rm -f result

                # Run garbage collection to clean up
                nix-collect-garbage -d

            else
                echo "Error: nix-build failed - result directory not found" >&2
                exit 1
            fi
        """
    ]

    try:
        subprocess.run(docker_cmd, check=True)
        # Verify if the output directory contains any files or
        # subdirectories.
        if any(output_dir.iterdir()):
            print(f"\nNix build completed. Results in: {output_dir}")
        else:
            print(f"Nix build failed.", file=sys.stderr)

    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Check if "docker" is available
    if not shutil.which('docker'):
        print("Error: Docker not found. Please install Docker first.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Package to Nix using Docker.")
    parser.add_argument("--generate", action="store_true", help="Generate the default.nix file.")

    args = parser.parse_args()

    if args.generate or not Path('default.nix').exists():
        # Check if "nix-prefetch-url" is available
        if not shutil.which("nix-prefetch-url"):
            print("nix-prefetch-url is NOT installed.")
            sys.exit(1)

        print("Generating default.nix")
        pyproject_data = read_pyproject_toml()
        meta_dict = extract_project_meta(pyproject_data)
        dependencies_list = extract_project_dependencies(pyproject_data)
        defualt_nix_content, need_review = create_defualt_nix(dependencies_list, meta_dict)
        with open("default.nix", "w") as file:
            file.write(defualt_nix_content)

        print("default.nix file created successfully.")
        if need_review:
            print("\nThe following packages need manual review as they were not found on PyPI or had issues:")
            for pkg in need_review:
                print(f" - {pkg['name']}=={pkg['version']}")
            print("\nPlease review and add them manually to default.nix and re-run without the --generate.\n")
            sys.exit(1)

    # Clean up the volume to ensure consistent state
    cleanup_nix_store()
    build_nix_with_docker()

if __name__ == '__main__':
    main()
