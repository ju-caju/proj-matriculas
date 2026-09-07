"""Validate Conventional Commit subjects introduced by a pull request."""

import argparse
import re
import subprocess


SUBJECT = re.compile(
    r"^(?:feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\([a-z0-9][a-z0-9._/-]*\))?!?: [a-záàâãéêíóôõúç][^\n]*[^.\s]$"
)


def invalid_subjects(subjects):
    return [subject for subject in subjects if not SUBJECT.fullmatch(subject)]


def subjects_between(base, head):
    result = subprocess.run(
        ["git", "log", "--format=%s", f"{base}..{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("head")
    args = parser.parse_args()
    invalid = invalid_subjects(subjects_between(args.base, args.head))
    if invalid:
        print("Commits fora do padrão Conventional Commits em português:")
        for subject in invalid:
            print(f"- {subject}")
        print("Exemplo: fix: corrigir aviso de conflito")
        raise SystemExit(1)
    print("Mensagens de commit seguem o padrão.")


if __name__ == "__main__":
    main()
