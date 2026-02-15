#!/usr/bin/env python
"""
Helper script to add nonce attributes to all inline <script> tags in HTML templates.
This ensures CSP compliance for inline scripts in DejaCode.

Usage: python add_nonces_to_templates.py
"""

import re
from pathlib import Path

def add_nonce_to_scripts(file_path):
    """
    Add nonce="{{ request.csp_nonce }}" attribute to inline <script> tags.
    Skips script tags that already have nonce attributes or have src attributes.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Pattern to match <script> tags without src attribute and without nonce
    # This matches: <script> but not <script src="..." or <script nonce="..."
    pattern = r'<script(?![^>]*(?:src|nonce)[^>]*?)>'
    
    # Replace with <script nonce="{{ request.csp_nonce }}">
    updated_content = re.sub(
        pattern,
        '<script nonce="{{ request.csp_nonce }}">',
        content
    )
    
    # Only write if changes were made
    if updated_content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        return True
    return False

def main():
    """Find and update all HTML template files with inline scripts."""
    
    # Find all HTML files in templates directories
    templates_dir = Path('.')
    html_files = list(templates_dir.glob('**/templates/**/*.html'))
    
    updated_count = 0
    total_count = 0
    
    for html_file in sorted(html_files):
        total_count += 1
        if add_nonce_to_scripts(html_file):
            updated_count += 1
            print(f"✓ Updated: {html_file}")
        else:
            print(f"  Skipped: {html_file}")
    
    print(f"\n✓ Processed {total_count} files, updated {updated_count} files with nonce attributes")

if __name__ == '__main__':
    main()
