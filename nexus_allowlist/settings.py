import os

APT_REMOTE_URL = os.getenv("APT_REMOTE_URL", "http://deb.debian.org/debian")
APT_DISTRO = os.getenv("APT_DISTRO", "bookworm")
ALLOWED_ARCHIVES = os.getenv(
    "APT_ALLOWED_ARCHIVES", "main,contrib,non-free-firmware,non-free"
).split(",")
