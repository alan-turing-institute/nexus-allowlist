#!/usr/bin/env sh

export NEXUS_DATA_DIR=/nexus-data
export ALLOWLIST_DIR=/allowlists
export PYPI_ALLOWLIST="$ALLOWLIST_DIR"/pypi.allowlist
export CRAN_ALLOWLIST="$ALLOWLIST_DIR"/cran.allowlist
export APT_ALLOWLIST="$ALLOWLIST_DIR"/apt.allowlist

timestamp() {
    date -Is
}

hashes() {
    md5sum $PYPI_ALLOWLIST $CRAN_ALLOWLIST
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

# Print version
nexus-allowlist --version

# Initial configuration
if [ -f "$NEXUS_DATA_DIR/admin.password" ]; then
    echo "$(timestamp) Initial password file present, running initial configuration"
    nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-path "$NEXUS_PATH" --nexus-port "$NEXUS_PORT" change-initial-password --path "$NEXUS_DATA_DIR"
    nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-path "$NEXUS_PATH" --nexus-port "$NEXUS_PORT" initial-configuration --packages "$NEXUS_PACKAGES" --pypi-package-file "$PYPI_ALLOWLIST" --cran-package-file "$CRAN_ALLOWLIST" --apt-package-file "$APT_ALLOWLIST"
else
    echo "$(timestamp) No initial password file found, skipping initial configuration"
fi

# Test authentication
if ! nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-path "$NEXUS_PATH" --nexus-port "$NEXUS_PORT" test-authentication; then
    echo "$(timestamp) API authentication test failed, exiting"
    exit 1
fi

if [ -n "$ENTR_FALLBACK" ]; then
    echo "$(timestamp) Using fallback file monitoring"
    # Run allowlist configuration now
    nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-path "$NEXUS_PATH" --nexus-port "$NEXUS_PORT" update-allowlists --packages "$NEXUS_PACKAGES" --pypi-package-file "$PYPI_ALLOWLIST" --cran-package-file "$CRAN_ALLOWLIST" --apt-package-file "$APT_ALLOWLIST"
    # Periodically check for modification of allowlist files and run configuration again when they are
    hash=$(hashes)
    while true; do
        new_hash=$(hashes)
        if [ "$hash" != "$new_hash" ]; then
            nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-path "$NEXUS_PATH" --nexus-port "$NEXUS_PORT" update-allowlists --packages "$NEXUS_PACKAGES" --pypi-package-file "$PYPI_ALLOWLIST" --cran-package-file "$CRAN_ALLOWLIST" --apt-package-file "$APT_ALLOWLIST"
            hash=$new_hash
        fi
        sleep 5
    done
else
    echo "$(timestamp) Using entr for file monitoring"
    # Run allowlist configuration now, and again whenever allowlist files are modified
    find "$ALLOWLIST_DIR"/*.allowlist | entr -n nexus-allowlist --admin-password "$NEXUS_ADMIN_PASSWORD" --nexus-host "$NEXUS_HOST" --nexus-path "$NEXUS_PATH" --nexus-port "$NEXUS_PORT" update-allowlists --packages "$NEXUS_PACKAGES" --pypi-package-file "$PYPI_ALLOWLIST" --cran-package-file "$CRAN_ALLOWLIST" --apt-package-file "$APT_ALLOWLIST"
fi
