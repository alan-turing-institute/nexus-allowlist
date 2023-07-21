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
echo "$(timestamp) Nexus is running"

# Initial configuration
if [ -f "$NEXUS_DATA_DIR/admin.password" ]; then
    echo "$(timestamp) Initial password file present, running initial configuration"
    nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" change-initial-password --path "$NEXUS_DATA_DIR"
    nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" initial-configuration --packages "$NEXUS_PACKAGES" --pypi-package-file "$ALLOWLIST_DIR/pypi.allowlist" --cran-package-file "$ALLOWLIST_DIR/cran.allowlist"
else
    echo "$(timestamp) No initial password file found, skipping initial configuration"
fi

# Test authentication
if ! nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" test-authentication; then
    echo "$(timestamp) API authentication test failed, exiting"
    exit 1
fi

# Run allowlist configuration now, and again whenever allowlist files are modified
find "$ALLOWLIST_DIR"/*.allowlist | entr -n nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-port "$NEXUS_PORT" update-allowlists --packages "$NEXUS_PACKAGES" --pypi-package-file "$PYPI_ALLOWLIST" --cran-package-file "$CRAN_ALLOWLIST"
