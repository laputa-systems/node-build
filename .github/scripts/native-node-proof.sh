#!/bin/sh
set -eu

target=$1
jobs=$2
printf 'Building %s with %s jobs\n' "$target" "$jobs"
make doctor TARGET="$target"
make build TARGET="$target" JOBS="$jobs" &
compile=$!
log="build/$target/make.log"
while kill -0 "$compile" 2>/dev/null; do
    sleep 60
    uptime
    ps -o pid,ppid,time,stat,comm -A |
        awk 'NR == 1 || $5 ~ /(^|\/)(clang[^/]*|cc1plus|g?make|ld[^/]*|node)$/'
    if [ -s "$log" ]; then
        wc -c "$log"
        tail -n 2 "$log"
    fi
done
if wait "$compile"; then
    make verify TARGET="$target"
else
    status=$?
    if [ -s "$log" ]; then tail -n 40 "$log"; fi
    exit "$status"
fi
