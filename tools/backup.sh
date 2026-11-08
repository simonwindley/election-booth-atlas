#!/bin/zsh
# Back up the Election Analyser folder to Cloudflare R2 (and, if plugged in, an external drive) with rclone.
#
#   tools/backup.sh            dry run: lists what would change, copies nothing
#   tools/backup.sh --go       does it
#
# One-time setup (in your own Terminal; keys never go in chat or git):
#   rclone config create r2 s3 provider=Cloudflare access_key_id=<KEY_ID> secret_access_key=<SECRET> \
#       endpoint=https://23be674d3cee1410a017ae36445adb3a.r2.cloudflarestorage.com acl=private no_check_bucket=true
#
# Mirrors the folder into r2:eba-raw/election-analyser. Files deleted or overwritten locally are not lost:
# the previous copy moves to r2:eba-raw/_superseded/<date>/. Left out: .git (GitHub has it), _to_delete,
# _incoming and macOS clutter. raw/aes (Australian Election Study unit records) is included: the bucket is private to
# this account, which keeps the data safe without passing it on (ADA terms). Never make the bucket public.
set -e
SRC="$HOME/Documents/Election Analyser"
BUCKET="r2:eba-raw"
DRIVE="${EBA_DRIVE:-/Volumes/Expansion}"   # the external drive (skipped if not plugged in)
STAMP=$(date +%Y-%m-%d_%H%M)
MODE=(--dry-run); [[ "$1" == "--go" ]] && MODE=()
COMMON=(--exclude ".git/**" --exclude "_to_delete/**" --exclude "_incoming/**" --exclude ".DS_Store" --exclude "**/__pycache__/**" --exclude "*.pyc" --exclude "**/.~lock*" --exclude "~\$*" --fast-list --transfers 8 --progress)

echo "== Cloudflare R2 (${MODE:-live})"
rclone sync "$SRC" "$BUCKET/election-analyser" "${COMMON[@]}" \
  --backup-dir "$BUCKET/_superseded/$STAMP" "${MODE[@]}"

if [[ -n "$DRIVE" && -d "$DRIVE" ]]; then
  echo "== External drive: $DRIVE (${MODE:-live})"
  rclone sync "$SRC" "$DRIVE/Election Booth Atlas/Election Analyser" "${COMMON[@]}" \
    --backup-dir "$DRIVE/Election Booth Atlas/_superseded/$STAMP" "${MODE[@]}"
else
  echo "(external drive not plugged in: $DRIVE — skipped)"
fi
