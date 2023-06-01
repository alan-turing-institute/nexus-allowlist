#!/usr/bin/env sh
ls ./allowlists/*.allowlist | entr -n python3 configure_nexus.py --help
