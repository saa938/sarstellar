#!/usr/bin/env bash
# Pull stage outputs from the Modal Volume into ../raw (outside the repo; large files stay out of git).
#   science/pull.sh [stage ...]        (default: every stage in modal_app/stage_defs.py)
# Each file is retried; a stage is reported COMPLETE only when stage.json, cube.npz and every
# image listed in stage.json are present.
set -uo pipefail
cd "$(dirname "$0")/.."
RAW="${RAW:-../raw}"
mkdir -p "$RAW/_ref"
stages=("$@")
if [ ${#stages[@]} -eq 0 ]; then
  stages=($(python3 -c "import sys; sys.path.insert(0,'.'); from modal_app.stage_defs import STAGES; print(' '.join(STAGES))"))
fi

get() {  # get <volume path> <local path>, 3 tries
  for _ in 1 2 3; do
    modal volume get --force sarstellar-data "$1" "$2" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}
export -f get

pull_one() {
  local s="$1" raw="$2"
  mkdir -p "$raw/$s"
  get "dance/$s/stage.json" "$raw/$s/stage.json" || { echo "$s: no stage.json yet"; return; }
  for f in cube.npz moves.npz highlight.json refs.npz; do get "dance/$s/$f" "$raw/$s/$f" || true; done
  rm -rf "$raw/$s/img"; mkdir -p "$raw/$s/img"
  get "dance/$s/img" "$raw/$s/" || true
  python3 - "$raw/$s" <<'EOF'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
info = json.loads((d / "stage.json").read_text())
need = ["cube.npz", "img/thumb.webp"] + info.get("render", {}).get("files", [])
missing = [n for n in need if not (d / n).exists()]
print(f"{d.name}: {'COMPLETE' if not missing else 'MISSING ' + ' '.join(missing[:4])}"
      f"{' moves' if (d / 'moves.npz').exists() else ''}{' refs' if (d / 'refs.npz').exists() else ''}")
EOF
}
export -f pull_one

printf '%s\n' "${stages[@]}" | xargs -P 4 -I{} bash -c 'pull_one "$@"' _ {} "$RAW"
for f in moves_report.json run_stats.json; do get "dance_ref/$f" "$RAW/_ref/$f" || true; done
get "dance/_constellation.npz" "$RAW/_constellation.npz" || true
ls "$RAW/_ref"
