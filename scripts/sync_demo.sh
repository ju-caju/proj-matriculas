#!/usr/bin/env bash
# Advance demo to an already-validated main commit without rewriting history.
set -euo pipefail

release_sha=${1:?Informe o SHA validado de main.}
git fetch origin main demo
release_sha=$(git rev-parse --verify "${release_sha}^{commit}")
main_sha=$(git rev-parse origin/main)

if [[ "$release_sha" != "$main_sha" ]]; then
  echo 'main avançou. A execução do commit mais recente atualizará a demo.'
  exit 0
fi

if ! git merge-base --is-ancestor origin/demo "$release_sha"; then
  echo 'demo contém commits fora de main. Integre-os por PR antes de sincronizar.' >&2
  exit 1
fi

git push origin "$release_sha:refs/heads/demo"
echo "demo sincronizada com main em $release_sha"
