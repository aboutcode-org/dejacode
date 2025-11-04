#!/usr/bin/env python3
"""
Generates a Nix expression (default.nix) from the
pyproject.toml file that is used to build the Python package for NixOS and
put it under the project root.

Requirement:
 - toml
 - requests
 - Docker
 - nix-prefetch-url

 To install the required Python packages, run:

    pip install toml requests

To install Docker, follow the instructions at:
    https://docs.docker.com/get-docker/

To install "nix-prefetch-url", follow the following instructions:
    # Install Nix in single-user mode
    curl -L https://nixos.org/nix/install | sh -s -- --no-daemon

    # Source nix in your current shell
    . ~/.nix-profile/etc/profile.d/nix.sh

    # Reload your shell or open new terminal
    source ~/.bashrc

    # Verify nix-prefetch-url works
    which nix-prefetch-url

To run the script:

    python build_nix_docker.py

It will create a `default.nix` file in the project root if it does not
already exist.

Options:
--------
`--generate` - Creates or overwrites default.nix in the project root.

    python build_nix_docker.py --generate

`--test` - Tests the build using Docker.

    python build_nix_docker.py --test


The `--test` flag will use Docker to run the Nix build in a clean
environment. It will run `nix-build` inside a Docker container to ensure
that the default.nix file is valid and can successfully build the package.
It will then do cleanup by removing the `nix-store` Docker volume.


Once the default.nix is generated, one can build/install the package by
using:

    Build the package

        nix-build default.nix

    The above command will create a symlink named `result` in the current
    directory pointing to the build output in the Nix store.
    Run the binary directly

        ./result/bin/dejacode
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests


def read_pyproject_toml():
    # Read the pyproject.toml file to extract project metadata.
    import toml

    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("Error: pyproject.toml not found in current directory", file=sys.stderr)
        sys.exit(1)

    with pyproject_path.open("r") as f:
        pyproject_data = toml.load(f)

    return pyproject_data


def extract_project_meta(pyproject_data):
    # Extract project metadata from pyproject.toml data.
    project_data = pyproject_data["project"]
    name = project_data.get("name")
    version = project_data.get("version")
    description = project_data.get("description")
    authors = project_data.get("authors")
    author_names = [author.get("name", "") for author in authors if "name" in author]
    author_str = ", ".join(author_names)

    meta_dict = {"name": name, "version": version, "description": description, "author": author_str}

    return meta_dict


def extract_project_dependencies(pyproject_data):
    # Extract project dependencies from pyproject.toml data.
    project_data = pyproject_data["project"]
    dependencies = project_data.get("dependencies", [])
    optional_dependencies = project_data.get("optional-dependencies", {})
    dev_optional_deps = optional_dependencies.get("dev", [])
    all_dep = dependencies + dev_optional_deps
    dependencies_list = []

    for dep in all_dep:
        name_version = dep.split("==")
        name = name_version[0]
        version = name_version[1]
        tmp_dict = {}
        tmp_dict["name"] = name
        tmp_dict["version"] = version
        dependencies_list.append(tmp_dict)

    if len(all_dep) != len(dependencies_list):
        raise ValueError("Dependency extraction mismatch")
    return dependencies_list


def create_defualt_nix(dependencies_list, meta_dict):
    # Create a default.nix
    nix_content = """
{
  pkgs ? import <nixpkgs> { },
}:

let
  python = pkgs.python313;

  # Helper function to create packages with specific versions and disabled tests
  buildCustomPackage = { pname, version, format ? "wheel", src, ... }@attrs:
    python.pkgs.buildPythonPackage ({
        inherit pname version format src;
        doCheck = false;
        doInstallCheck = false;
        doPytestCheck = false;
        pythonImportsCheck = [];
    } // attrs);

  pythonOverlay = self: super: {
"""
    need_review_packages_list = []
    deps_size = len(dependencies_list)
    for idx, dep in enumerate(dependencies_list):
        print("Processing {}/{}: {}".format(idx + 1, deps_size, dep["name"]))
        name = dep["name"]
        version = dep["version"]
        # Handle 'django_notifications_patched', 'django-rest-hooks' and
        # 'python_ldap' separately
        if (
            name == "django-rest-hooks"
            or name == "django_notifications_patched"
            or name == "python_ldap"
        ):
            if name == "django-rest-hooks" and version == "1.6.1":
                nix_content += "    " + name + " = python.pkgs.buildPythonPackage {\n"
                nix_content += '        pname = "django-rest-hooks";\n'
                nix_content += '        version = "1.6.1";\n'
                nix_content += '        format = "wheel";\n'
                nix_content += "        src = pkgs.fetchurl {\n"
                nix_content += '          url = "https://github.com/aboutcode-org/django-rest-hooks/releases/download/1.6.1/django_rest_hooks-1.6.1-py2.py3-none-any.whl";\n'
                nix_content += (
                    '          sha256 = "1byakq3ghpqhm0mjjkh8v5y6g3wlnri2vvfifyi9ky36l12vqx74";\n'
                )
                nix_content += "        };\n"
                nix_content += "    };\n"
            elif name == "django_notifications_patched" and version == "2.0.0":
                nix_content += "    " + name + " = self.buildPythonPackage rec {\n"
                nix_content += '        pname = "django_notifications_patched";\n'
                nix_content += '        version = "2.0.0";\n'
                nix_content += '        format = "setuptools";\n'
                nix_content += "        doCheck = false;\n"
                nix_content += "        src = pkgs.fetchFromGitHub {\n"
                nix_content += '           owner = "dejacode";\n'
                nix_content += '           repo = "django-notifications-patched";\n'
                nix_content += '           rev = "2.0.0";\n'
                nix_content += '           url = "https://github.com/dejacode/django-notifications-patched/archive/refs/tags/2.0.0.tar.gz";\n'
                nix_content += (
                    '           sha256 = "sha256-RDAp2PKWa2xA5ge25VqkmRm8HCYVS4/fq2xKc80LDX8=";\n'
                )
                nix_content += "        };\n"
                nix_content += "    };\n"
            elif name == "python_ldap" and version == "3.4.5":
                nix_content += "    " + name + " = buildCustomPackage {\n"
                nix_content += '        pname = "python_ldap";\n'
                nix_content += '        version = "3.4.5";\n'
                nix_content += '        format = "setuptools";\n'
                nix_content += "        src = pkgs.fetchurl {\n"
                nix_content += '          url = "https://files.pythonhosted.org/packages/0c/88/8d2797decc42e1c1cdd926df4f005e938b0643d0d1219c08c2b5ee8ae0c0/python_ldap-3.4.5.tar.gz";\n'
                nix_content += (
                    '          sha256 = "16pplmqb5wqinzy4azbafr3iiqhy65qzwbi1hmd6lb7y6wffzxmj";\n'
                )
                nix_content += "        };\n"
                nix_content += "        nativeBuildInputs = with pkgs; [\n"
                nix_content += "        pkg-config\n"
                nix_content += "        python.pkgs.setuptools\n"
                nix_content += "        python.pkgs.distutils\n"
                nix_content += "        ];\n"
                nix_content += "        buildInputs = with pkgs; [ openldap cyrus_sasl ];\n"
                nix_content += "    };\n"
            else:
                need_review_packages_list.append(dep)
        else:
            url = "https://pypi.org/pypi/{name}/{version}/json".format(name=name, version=version)
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()

                url_section = data.get("urls", [])
                build_from_src = True
                package_added = False
                for component in url_section:
                    if component.get("packagetype") == "bdist_wheel":
                        whl_url = component.get("url")
                        if (
                            ("cp313" not in whl_url and "py3" not in whl_url)
                            or ("manylinux" not in whl_url and "-none-" not in whl_url)
                            or ("any.whl" not in whl_url and "x86_64" not in whl_url)
                        ):
                            continue
                        whl_sha256 = get_sha256_hash(whl_url)
                        nix_content += "    " + name + " = buildCustomPackage {\n"
                        nix_content += '        pname = "' + name + '";\n'
                        nix_content += '        version = "' + version + '";\n'
                        nix_content += '        format = "wheel";\n'
                        nix_content += "        src = pkgs.fetchurl {\n"
                        nix_content += '          url = "' + whl_url + '";\n'
                        nix_content += '          sha256 = "' + whl_sha256 + '";\n'
                        nix_content += "        };\n"
                        nix_content += "    };\n"
                        build_from_src = False
                        package_added = True
                        break

                if build_from_src:
                    for component in url_section:
                        if component.get("packagetype") == "sdist":
                            sdist_url = component.get("url")
                            sdist_sha256 = get_sha256_hash(sdist_url)
                            nix_content += "    " + name + " = buildCustomPackage {\n"
                            nix_content += '        pname = "' + name + '";\n'
                            nix_content += '        version = "' + version + '";\n'
                            nix_content += '        format = "setuptools";\n'
                            nix_content += "        src = pkgs.fetchurl {\n"
                            nix_content += '          url = "' + sdist_url + '";\n'
                            nix_content += '          sha256 = "' + sdist_sha256 + '";\n'
                            nix_content += "        };\n"
                            nix_content += "    };\n"
                            package_added = True
                            break
                if not package_added:
                    need_review_packages_list.append(dep)
            except requests.exceptions.RequestException:
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

    nix_content += '    name = "' + meta_dict["name"] + '";\n'
    nix_content += '    version = "' + meta_dict["version"] + '";\n'

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

    # Add PostgreSQL to buildInputs to ensure libpq is available at runtime
    buildInputs = with pkgs; [
      postgresql
    ];

    # This wrapper ensures the PostgreSQL libraries are available at runtime
    makeWrapperArgs = [
      "--set LD_LIBRARY_PATH ${pkgs.postgresql.lib}/lib"
    ];

    propagatedBuildInputs = with pythonWithOverlay.pkgs; [
"""

    for dep in dependencies_list:
        name = dep["name"]
        nix_content += "      " + name + "\n"

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
    # Get SHA256 hash of a file using nix-prefetch-url.
    try:
        nix_prefetch_url_path = shutil.which("nix-prefetch-url")
        if not nix_prefetch_url_path:
            print("Error: nix-prefetch-url command not found. Make sure nix is installed.")
            return None
        result = subprocess.run(  # noqa: S603
            [nix_prefetch_url_path, url],
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running nix-prefetch-url for {url}: {e}")
        return None
    except FileNotFoundError:
        print("Error: nix-prefetch-url command not found. Make sure nix is installed.")
        return None


def cleanup_nix_store():
    # Remove the nix-store volume to ensure clean state
    try:
        docker_path = shutil.which("docker")
        if not docker_path:
            print("Error: docker command not found. Make sure docker is installed.")
            return None
        subprocess.run([docker_path, "volume", "rm", "nix-store"], check=True, capture_output=True)  # noqa: S603
        print("Cleaned up nix-store volume.")
    except subprocess.CalledProcessError as e:
        # Volume might not exist, which is fine
        if "no such volume" not in e.stderr.decode().lower():
            print(f"Warning: Could not remove nix-store volume: {e.stderr.decode()}")
        pass


def build_nix_with_docker():
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.getcwd()}:/workspace",
        "-v",
        "nix-store:/nix",
        "-w",
        "/workspace",
        "nixos/nix",
        "/bin/sh",
        "-c",
        """set -e
            # Update nix-channel to get latest packages
            nix-channel --update > /dev/null 2>&1

            # Run nix-build, only show errors
            nix-build default.nix -o result 2>&1 | grep -E "(error|fail|Error|Fail)" || true

            # Check if build was successful
            if [ -d result ]; then
                echo "Build successfully using default.nix."
                echo "Performing cleanup..."
                # Perform cleanup
                # Remove the result symlink
                rm -f result

                # Run garbage collection to clean up
                # supress logs
                nix-collect-garbage -d > /dev/null 2>&1
                echo "Cleanup completed."
            else
                echo "Error: nix-build failed" >&2
                exit 1
            fi
        """,
    ]

    try:
        subprocess.run(docker_cmd, check=True, shell=False)  # noqa: S603
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Check if "docker" is available
    if not shutil.which("docker"):
        print("Error: Docker not found. Please install Docker first.", file=sys.stderr)
        sys.exit(1)

    # Get the directory where the current script is located (which is located in etc/scripts)
    script_dir = Path(__file__).parent.resolve()
    # Go up two levels from etc/scripts/
    project_root = script_dir.parent.parent
    os.chdir(project_root)

    parser = argparse.ArgumentParser(description="Package to Nix")
    # Add optional arguments
    parser.add_argument("--generate", action="store_true", help="Generate the default.nix file.")
    parser.add_argument(
        "--test", action="store_true", help="Test to build from the default.nix file."
    )

    # Parse arguments
    args = parser.parse_args()

    if args.generate or not Path("default.nix").exists():
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
            print(
                "\nThe following packages need manual review"
                "as they were not found on PyPI or had issues:"
            )
            for pkg in need_review:
                print(f" - {pkg['name']}=={pkg['version']}")
            print(
                "\nPlease review and add them manually to"
                "default.nix and re-run without the --generate.\n"
            )
            sys.exit(1)

    if args.test:
        print("Testing the default.nix build...")
        cleanup_nix_store()
        build_nix_with_docker()


if __name__ == "__main__":
    main()
