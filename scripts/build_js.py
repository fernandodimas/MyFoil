#!/usr/bin/env python3
"""
Build script for MyFoil JS bundles.
Concatenates source files into optimized bundles.

Usage: python scripts/build_js.py
"""
import os
import sys

JS_DIR = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'js')

BUNDLES = {
    'core.js': {
        'header': '/**\n * MyFoil Core Bundle\n * base.js + system_status.js\n * DO NOT EDIT - run: python scripts/build_js.py\n */\n',
        'files': ['base.js', 'system_status.js'],
    },
    'settings.js': {
        'header': '/**\n * MyFoil Settings Bundle\n * tokens.js + settings_bundled.js\n * DO NOT EDIT - run: python scripts/build_js.py\n */\n',
        'files': ['tokens.js', 'settings_bundled.js'],
    },
}


def build_bundle(name, config):
    header = config['header']
    parts = [header]
    for fname in config['files']:
        fpath = os.path.join(JS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  WARNING: {fname} not found, skipping")
            continue
        with open(fpath, 'r') as f:
            content = f.read()
        parts.append(f'\n// ============================================================\n// {fname}\n// ============================================================\n')
        parts.append(content)
        parts.append('\n')
    output = os.path.join(JS_DIR, name)
    with open(output, 'w') as f:
        f.write(''.join(parts))
    size = os.path.getsize(output)
    print(f"  Built {name} ({size:,} bytes)")


def main():
    print("Building JS bundles...")
    for name, config in BUNDLES.items():
        build_bundle(name, config)
    print("Done.")


if __name__ == '__main__':
    main()
