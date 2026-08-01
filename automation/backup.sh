#!/bin/bash

# 環境に合わせて設定する（未設定なら iCloud Drive 配下を既定とする）
DEST_DIR="${THE_CAPTION_BACKUP_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/THE-CAPTION-DATA_LOG/}"
DATE_STAMP=$(date +%Y%m%d)

case "$1" in
    prd)
        BASE_SRC="${THE_CAPTION_PRD_DIR:-$HOME/repos/the-caption}"
        PREFIX=""
        EXEC_ARCHIVE=1
        ;;
    dev)
        BASE_SRC="${THE_CAPTION_DEV_DIR:-$HOME/repos/the-caption-dev}"
        PREFIX="dev_"
        EXEC_ARCHIVE=0
        ;;
    *)
        echo "Usage: $0 {prd|dev}"
        exit 1
        ;;
esac

if [ ! -d "$DEST_DIR" ]; then
    echo "[Error] Destination directory does not exist: $DEST_DIR"
    exit 1
fi

if [ "$EXEC_ARCHIVE" -eq 1 ]; then
    mkdir -p "$DEST_DIR/Archive"
    echo "[Info] Archiving existing files in $DEST_DIR..."
    find "$DEST_DIR" -maxdepth 1 -type f \( -name "*.log" -o -name "*.tar.gz" \) -exec mv -v {} "$DEST_DIR/Archive/" \;
fi

SRC_LOG_DIR="$BASE_SRC/logs"
if [ -d "$SRC_LOG_DIR" ]; then
    [ -f "$SRC_LOG_DIR/finance_report.log" ] && cp "$SRC_LOG_DIR/finance_report.log" "$DEST_DIR/${PREFIX}finance_report_${DATE_STAMP}.log"
    [ -f "$SRC_LOG_DIR/llm_trace.log" ] && cp "$SRC_LOG_DIR/llm_trace.log" "$DEST_DIR/${PREFIX}llm_trace_${DATE_STAMP}.log"
    [ -f "$SRC_LOG_DIR/cron_panic.log" ] && cp "$SRC_LOG_DIR/cron_panic.log" "$DEST_DIR/${PREFIX}cron_panic_${DATE_STAMP}.log"
else
    echo "[Warn] Log directory not found: $SRC_LOG_DIR"
fi

if [ -d "$BASE_SRC/data" ]; then
    cd "$BASE_SRC" || exit 1
    tar cvzf data.tar.gz data
    cp "$BASE_SRC/data.tar.gz" "$DEST_DIR/${PREFIX}data_${DATE_STAMP}.tar.gz"
else
    echo "[Error] Data directory not found: $BASE_SRC/data"
fi
