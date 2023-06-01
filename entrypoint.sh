#!/usr/bin/env sh

echo "$NEXUS_ADMIN_PASSWORD"
echo "$NEXUS_TIER"
echo "$NEXUS_HOST"
echo "$NEXUS_PORT"

export NEXUS_DATA_DIR=/nexus-data
export ALLOWLIST_DIR=/allowlists

ls "$ALLOWLIST_DIR"/*.allowlist
ls "$ALLOWLIST_DIR"

# Wait for Nexus
until curl "$NEXUS_HOST":"$NEXUS_PORT"; do
    echo "Waiting for Nexus"
    sleep 10
done

# Initial configuration
if [ -f "$NEXUS_DATA_DIR/admin.password" ]; then
    echo "Initial password file present, running initial configuration"
    python3 configure_nexus.py --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" change-initial-password --path "$NEXUS_DATA_DIR"
    python3 configure_nexus.py --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" initial-configuration --tier "$NEXUS_TIER" --pypi-package-file "$ALLOWLIST_DIR/pypi.allowlist" --cran-package-file "$ALLOWLIST_DIR/cran.allowlist"
fi

# Rerun allowlist configuration whenever allowlist files are modified
ls "$ALLOWLIST_DIR"/*.allowlist | entr -n python3 configure_nexus.py --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" update-allowlists --tier "$NEXUS_TIER" --pypi-package-file "$ALLOWLIST_DIR/pypi.allowlist" --cran-package-file "$ALLOWLIST_DIR/cran.allowlist"
