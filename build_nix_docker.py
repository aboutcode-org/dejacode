#!/usr/bin/env python3
"""
Use Docker container to run nix-build.
Using Docker approach to ensure a consistent and isolated build environment.

To run the script:

    python build_nix_docker.py

This script will run nix-build and place the built results in the
dist/nix/ directory, it will then run nix-collect-garbage for cleanup.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


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


if __name__ == '__main__':
    # Check if "docker" is available
    if not shutil.which('docker'):
        print("Error: Docker not found. Please install Docker first.", file=sys.stderr)
        sys.exit(1)

    # Check if default.nix exists
    if not Path('default.nix').exists():
        print("Error: default.nix not found in current directory", file=sys.stderr)
        sys.exit(1)

    # Clean up the volume to ensure consistent state
    cleanup_nix_store()

    build_nix_with_docker()
