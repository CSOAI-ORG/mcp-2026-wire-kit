#!/bin/bash
# Content gates for mcp-2026-wire-kit (required by the global pre-push hook).
# Real checks: private keys, secret tokens, internal codenames, py compile.
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 1
cd "$ROOT" || exit 1

secret_scan()  { printf '%s' "$1" | grep -qE '^\+.*-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----'; }
token_scan()   { printf '%s' "$1" | grep -qE '^\+.*(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{32,})'; }
codename_scan(){ printf '%s' "$1" | grep -qiE '^\+.*(SOVOS|OWEM|sov6|dagon)'; }
py_compiles()  { python3 - "$1" <<'PY' >/dev/null 2>&1
import sys; compile(open(sys.argv[1],'rb').read(), sys.argv[1], 'exec')
PY
}

if [ "${1:-}" = "--selftest" ]; then
  bad=0
  if secret_scan '+-----BEGIN ED25519 PRIVATE KEY-----
'; then echo "  ok secret gate detects private-key material"
  else echo "  x secret gate MISSED a private key"; bad=1; fi
  if secret_scan '+this line is ordinary documentation
'; then echo "  x secret gate false-positives on prose"; bad=1
  else echo "  ok secret gate stays quiet on prose"; fi
  tok=$(printf 'ghp_%s' 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
  if token_scan "+value $tok
"; then echo "  ok token gate detects github token"
  else echo "  x token gate MISSED a github token"; bad=1; fi
  if codename_scan '+text references SOVOS here
'; then echo "  ok codename gate detects internal codename"
  else echo "  x codename gate MISSED a codename"; bad=1; fi
  echo 'def ok(): pass' > /tmp/_gk_ok.py
  if py_compiles /tmp/_gk_ok.py; then echo "  ok py gate accepts valid python"
  else echo "  x py gate false-fails valid python"; bad=1; fi
  echo 'def broken(:' > /tmp/_gk_bad.py
  if py_compiles /tmp/_gk_bad.py; then echo "  x py gate MISSED syntax error"; bad=1
  else echo "  ok py gate rejects syntax errors"; fi
  rm -f /tmp/_gk_ok.py /tmp/_gk_bad.py
  exit $bad
fi

echo "pre-push: wire-kit content gates (selftest)…"
bash "$0" --selftest || { echo "pre-push: SELFTEST FAILED"; exit 1; }

fail=0
while read -r lref lsha rref rsha; do
  [ -z "${lref:-}" ] && continue
  case "$lsha" in 0000000000000000000000000000000000000000) continue ;; esac
  if [ "$rsha" = "0000000000000000000000000000000000000000" ] || ! git cat-file -e "$rsha" 2>/dev/null; then
    commits=$(git rev-list "$lsha" --not --remotes 2>/dev/null)
  else
    commits=$(git rev-list "$rsha".."$lsha" --not --remotes 2>/dev/null)
  fi
  [ -z "$commits" ] && continue
  added=$(printf '%s\n' "$commits" | xargs -I{} git show {} --unified=0 --pretty=format: 2>/dev/null | grep '^+' | grep -v '^+++')
  if [ -n "$added" ]; then
    secret_scan "$added" && { echo "  x PRIVATE KEY material in diff"; fail=1; }
    token_scan "$added" && { echo "  x secret token in diff"; fail=1; }
    codename_scan "$added" && { echo "  x internal codename in diff (public repo)"; fail=1; }
  fi
  files=$(printf '%s\n' "$commits" | xargs -I{} git diff-tree --no-commit-id --name-only -r {} 2>/dev/null | sort -u)
  while IFS= read -r f; do
    case "$f" in *.py) [ -f "$f" ] && ! py_compiles "$f" && { echo "  x $f does not compile"; fail=1; } ;; esac
  done <<EOT
$files
EOT
done
if [ "$fail" -eq 0 ]; then echo "  ok wire-kit gates clean"; fi
exit $fail
