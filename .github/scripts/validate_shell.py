#!/usr/bin/env python3

import concurrent.futures
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import yaml

EXCLUDE_DIRS = {".git"}

def get_bash_executable():
    which_bash = shutil.which("bash")
    if which_bash:
        return which_bash
    windows_git_bash = r"C:\Program Files\Git\bin\bash.exe"
    if os.path.exists(windows_git_bash):
        return windows_git_bash
    return "bash"

BASH_BIN = get_bash_executable()


def find_shell_files(root="."):
    for path in pathlib.Path(root).rglob("*.sh"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        yield path


def check_file(path):
    result = subprocess.run(
        [BASH_BIN, "-n", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return str(path), result.stderr.strip()
    return str(path), None


def extract_inline_scripts(root="."):
    """Extract inline run: blocks from workflows and composite actions."""
    patterns = [
        pathlib.Path(root) / ".github" / "workflows",
        pathlib.Path(root) / ".github" / "actions",
    ]
    yaml_files = []
    for p in patterns:
        if p.exists():
            yaml_files.extend(p.rglob("*.yml"))
            yaml_files.extend(p.rglob("*.yaml"))

    scripts = []

    def walk_nodes(node, file_path, prefix=""):
        if isinstance(node, dict):
            if "run" in node and isinstance(node["run"], str):
                shell = node.get("shell", "bash")
                if "bash" in shell or "sh" in shell:
                    name = node.get("name", "unnamed step")
                    desc = f"{file_path} > {prefix}{name}"
                    scripts.append((desc, node["run"]))
            for k, v in node.items():
                walk_nodes(v, file_path, f"{prefix}{k}/" if prefix else f"{k}/")
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                walk_nodes(item, file_path, f"{prefix}[{idx}]/")

    for yf in sorted(yaml_files):
        try:
            with yf.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
                if data:
                    walk_nodes(data, str(yf))
        except Exception:
            continue

    return scripts


def check_inline_script(item):
    desc, script = item
    # Replace GitHub Actions expressions like ${{ ... }} with safe token
    sanitized = re.sub(r"\$\{\{[^}]*\}\}", '"__GH_EXPR__"', script)

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as tf:
        tf.write(sanitized)
        tf_name = tf.name

    try:
        result = subprocess.run(
            [BASH_BIN, "-n", tf_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return desc, result.stderr.strip()
        return desc, None
    finally:
        if os.path.exists(tf_name):
            try:
                os.remove(tf_name)
            except OSError:
                pass


def main():
    # 1. Check standalone .sh scripts
    sh_files = sorted(find_shell_files())
    status = 0

    if sh_files:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(check_file, sh_files)
            for path, error in results:
                if error:
                    print(f"Syntax error in shell file: {path}")
                    print(f"  {error}")
                    status = 1
        print(f"Checked {len(sh_files)} standalone shell script(s).")
    else:
        print("Checked 0 standalone shell script(s).")

    # 2. Check inline workflow & action scripts
    inline_scripts = extract_inline_scripts()
    if inline_scripts:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(check_inline_script, inline_scripts)
            for desc, error in results:
                if error:
                    print(f"Syntax error in inline script: {desc}")
                    print(f"  {error}")
                    status = 1
        print(f"Checked {len(inline_scripts)} inline shell block(s).")
    else:
        print("No inline shell blocks found.")

    return status


if __name__ == "__main__":
    sys.exit(main())
