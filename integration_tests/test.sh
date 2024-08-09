#! /usr/bin/env bash
docker build -t nexus_allowlist_bats:latest .
docker run \
    --rm \
    -it \
    -v "$PWD/tests:/code" \
    --network host \
    nexus_allowlist_bats:latest \
    /code
