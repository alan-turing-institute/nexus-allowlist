#!/usr/bin/env sh

export NEXUS_DATA_DIR=/nexus-data
export ALLOWLIST_DIR=/allowlists
export PYPI_ALLOWLIST="$ALLOWLIST_DIR"/pypi.allowlist
export CRAN_ALLOWLIST="$ALLOWLIST_DIR"/cran.allowlist

timestamp() {
    date -Is
}

# Ensure allowlist files exist
if ! [ -f "$PYPI_ALLOWLIST" ]; then
    echo "$(timestamp) PyPI allowlist not found"
    exit 1
fi
if ! [ -f "$CRAN_ALLOWLIST" ]; then
    echo "$(timestamp) CRAN allowlist not found"
    exit 1
fi

# Wait for Nexus
until curl -s "$NEXUS_HOST":"$NEXUS_PORT" > /dev/null; do
    echo "$(timestamp) Waiting for Nexus"
    sleep 10
done
echo "$(timestamp) Connected to Nexus"

# Initial configuration
if [ -f "$NEXUS_DATA_DIR/admin.password" ]; then
    echo "$(timestamp) Initial password file present, running initial configuration"
    python3 configure_nexus.py --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" change-initial-password --path "$NEXUS_DATA_DIR"
    python3 configure_nexus.py --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" initial-configuration --packages "$NEXUS_PACKAGES" --pypi-package-file "$ALLOWLIST_DIR/pypi.allowlist" --cran-package-file "$ALLOWLIST_DIR/cran.allowlist"
else
    echo "$(timestamp) No initial password file found, skipping initial configuration"
fi

# Run allowlist configuration whenever allowlist files are modified
find "$ALLOWLIST_DIR"/*.allowlist | entr -np python3 configure_nexus.py --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" update-allowlists --packages "$NEXUS_PACKAGES" --pypi-package-file "$PYPI_ALLOWLIST" --cran-package-file "$CRAN_ALLOWLIST"
