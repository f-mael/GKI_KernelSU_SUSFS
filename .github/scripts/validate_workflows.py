#!/usr/bin/env python3

import pathlib
import sys

import yaml

WORKFLOW_DIR = pathlib.Path(".github/workflows")
ACTIONS_DIR = pathlib.Path(".github/actions")


def find_workflow_files():
    if not WORKFLOW_DIR.exists():
        return []
    return sorted(
        list(WORKFLOW_DIR.glob("*.yml")) + list(WORKFLOW_DIR.glob("*.yaml"))
    )


def find_action_files():
    if not ACTIONS_DIR.exists():
        return []
    return sorted(
        list(ACTIONS_DIR.rglob("action.yml")) + list(ACTIONS_DIR.rglob("action.yaml"))
    )


def check_jobs(data):
    errors = []
    jobs = data.get("jobs")

    if jobs is None:
        errors.append("missing top-level 'jobs' key")
        return errors

    if not isinstance(jobs, dict) or not jobs:
        errors.append("'jobs' must be a non-empty mapping")
        return errors

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"job '{job_name}': must be a mapping")
            continue

        if "runs-on" not in job and "uses" not in job:
            errors.append(f"job '{job_name}': missing 'runs-on' (or 'uses' for reusable workflows)")

        steps = job.get("steps")
        if steps is None:
            if "uses" not in job:
                errors.append(f"job '{job_name}': missing 'steps'")
            continue

        if not isinstance(steps, list):
            errors.append(f"job '{job_name}': 'steps' must be a list")
            continue

        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"job '{job_name}', step {index}: must be a mapping")
                continue
            if "run" not in step and "uses" not in step:
                name = step.get("name", f"step {index}")
                errors.append(f"job '{job_name}', '{name}': missing 'run' or 'uses'")

    return errors


def check_action(data):
    errors = []
    if "runs" not in data:
        errors.append("missing top-level 'runs' key")
        return errors

    runs = data.get("runs")
    if not isinstance(runs, dict):
        errors.append("'runs' must be a mapping")
        return errors

    using = runs.get("using")
    if not using:
        errors.append("missing 'runs.using' key")
    elif using == "composite":
        steps = runs.get("steps")
        if steps is None:
            errors.append("composite action missing 'runs.steps'")
        elif not isinstance(steps, list):
            errors.append("'runs.steps' must be a list")
        else:
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    errors.append(f"step {index}: must be a mapping")
                    continue
                if "run" not in step and "uses" not in step:
                    name = step.get("name", f"step {index}")
                    errors.append(f"step '{name}': missing 'run' or 'uses'")

    return errors


def check_file(path, is_action=False):
    errors = []
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        if mark is not None:
            errors.append(f"YAML error at line {mark.line + 1}, column {mark.column + 1}: {error}")
        else:
            errors.append(f"YAML error: {error}")
        return errors

    if not isinstance(data, dict):
        errors.append("file does not parse to a mapping at the top level")
        return errors

    if is_action:
        errors.extend(check_action(data))
    else:
        # PyYAML parses the unquoted key 'on' as boolean True in YAML 1.1.
        if "on" not in data and True not in data:
            errors.append("missing top-level 'on' trigger key")
        errors.extend(check_jobs(data))

    return errors


def main():
    wf_files = find_workflow_files()
    action_files = find_action_files()

    if not wf_files and not action_files:
        print("No workflow or action files found.")
        return 0

    status = 0
    for path in wf_files:
        errors = check_file(path, is_action=False)
        if errors:
            status = 1
            print(f"Issues in workflow: {path}")
            for error in errors:
                print(f"  {error}")

    for path in action_files:
        errors = check_file(path, is_action=True)
        if errors:
            status = 1
            print(f"Issues in action: {path}")
            for error in errors:
                print(f"  {error}")

    print(f"Checked {len(wf_files)} workflow file(s) and {len(action_files)} action file(s).")
    return status


if __name__ == "__main__":
    sys.exit(main())
