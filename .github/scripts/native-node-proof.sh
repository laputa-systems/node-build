#!/bin/sh
set -eu

target=$1
jobs=$2
make doctor TARGET="$target"
make build TARGET="$target" JOBS="$jobs" &
compile=$!
log="build/$target/make.log"
while kill -0 "$compile" 2>/dev/null; do
    sleep 30
    if [ -s "$log" ]; then tail -n 2 "$log"; fi
done
wait "$compile"
make verify TARGET="$target"
