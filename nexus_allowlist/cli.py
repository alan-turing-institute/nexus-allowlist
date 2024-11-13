#! /usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

from nexus_allowlist import actions
from nexus_allowlist.__about__ import __version__
from nexus_allowlist.exceptions import InitialPasswordError
from nexus_allowlist.nexus import NexusAPI

logging.basicConfig(
    format="{asctime} {levelname}: {message}",
    style="{",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    level=logging.INFO,
)


_ROLE_NAME = "nexus user"


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce allowlists for Nexus3")
    parser.add_argument(
        "--admin-password",
        type=str,
        required=True,
        help="Password for the Nexus 'admin' account",
    )
    parser.add_argument(
        "--nexus-host",
        type=str,
        default="localhost",
        help="Hostname of the Nexus server (default localhost)",
    )
    parser.add_argument(
        "--nexus-port",
        type=str,
        default="80",
        help="Port of the Nexus server (default 80)",
    )
    parser.add_argument(
        "--nexus-path",
        type=str,
        default="",
        help="Context path of the Nexus server (default /)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{parser.prog} {__version__}",
        help="Print the version and exit",
    )

    # Group of arguments for packages
    packages_parser = argparse.ArgumentParser(add_help=False)
    packages_parser.add_argument(
        "--packages",
        type=str,
        required=True,
        choices=["all", "selected"],
        help="Whether to allow 'all' packages or only 'selected' packages",
    )
    packages_parser.add_argument(
        "--pypi-package-file",
        type=Path,
        help=(
            "Path of the file of allowed PyPI packages, ignored when PACKAGES is all"
        ),
    )
    packages_parser.add_argument(
        "--cran-package-file",
        type=Path,
        help=(
            "Path of the file of allowed CRAN packages, ignored when PACKAGES is all"
        ),
    )
    packages_parser.add_argument(
        "--apt-package-file",
        type=Path,
        help="Path of the file of allowed APT packages, ignored when PACKAGES is all",
    )

    subparsers = parser.add_subparsers(title="subcommands", required=True)

    # sub-command for changing initial password
    parser_password = subparsers.add_parser(
        "change-initial-password", help="Change the initial admin password"
    )
    parser_password.add_argument(
        "--path",
        type=Path,
        default=Path("./nexus-data"),
        help="Path of the nexus-data directory [./nexus-data]",
    )
    parser_password.set_defaults(func=change_initial_password)

    # sub-command for authentication test
    parser_password = subparsers.add_parser(
        "test-authentication", help="Test authentication settings"
    )
    parser_password.set_defaults(func=test_authentiation)

    # sub-command for initial configuration
    parser_configure = subparsers.add_parser(
        "initial-configuration",
        help="Configure the Nexus repository",
        parents=[packages_parser],
    )
    parser_configure.set_defaults(func=initial_configuration)

    # sub-command for updating package allow lists
    parser_update = subparsers.add_parser(
        "update-allowlists",
        help="Update the Nexus package allowlists",
        parents=[packages_parser],
    )
    parser_update.set_defaults(func=update_allow_lists)

    args = parser.parse_args()

    args.func(args)


def change_initial_password(args: argparse.Namespace) -> None:
    """
    Change the initial password created during Nexus deployment

    The initial password is stored in a file called 'admin.password' which is
    automatically removed when the password is first changed.

    Args:
        args: Command line arguments

    raises:
        Exception: If 'admin.password' is not found
    """
    password_file_path = Path(f"{args.path}/admin.password")

    try:
        with password_file_path.open() as password_file:
            initial_password = password_file.read()
    except FileNotFoundError as exc:
        msg = "Initial password appears to have been already changed"
        raise InitialPasswordError(msg) from exc

    nexus_api = NexusAPI(
        password=initial_password,
        nexus_host=args.nexus_host,
        nexus_port=args.nexus_port,
        nexus_path=args.nexus_path,
    )

    nexus_api.change_admin_password(args.admin_password)


def test_authentiation(args: argparse.Namespace) -> None:
    nexus_api = NexusAPI(
        password=args.admin_password,
        nexus_host=args.nexus_host,
        nexus_port=args.nexus_port,
        nexus_path=args.nexus_path,
    )

    if not nexus_api.test_auth():
        sys.exit(1)


def initial_configuration(args: argparse.Namespace) -> None:
    """
    Initial Nexus configuration.

    This includes:
        - Deleting all respositories
        - Creating CRAN, APT and PyPI proxies
        - Deleting all content selectors and content selector privileges
        - Deleting all non-default roles
        - Creating a role
        - Giving anonymous users ONLY the previously defined role
        - Enabling anonymous access

    This does not configure the allowlists.

    Args:
        args: Command line arguments
    """
    actions.check_package_files(args)

    nexus_api = NexusAPI(
        password=args.admin_password,
        nexus_host=args.nexus_host,
        nexus_port=args.nexus_port,
        nexus_path=args.nexus_path,
    )

    # Ensure only desired repositories exist
    actions.recreate_repositories(nexus_api)

    # Delete non-default roles
    nexus_api.delete_all_custom_roles()

    # Create a role for nexus allowlist
    nexus_api.create_role(
        name=_ROLE_NAME,
        description="allows access to selected packages",
        privileges=[],
    )

    # Give anonymous users ONLY the nexus allowlist role
    nexus_api.update_anonymous_user_roles([_ROLE_NAME])

    # Enable anonymous access
    nexus_api.enable_anonymous_access()


def update_allow_lists(args: argparse.Namespace) -> None:
    """
    Update which packages anonymous users may access AFTER the initial, full
    configuration of the Nexus server.

    The following steps will occur:
        - Deleting all content selectors and content selector privileges
        - Creating content selectors and content selector privileges according
          to the packages setting and allowlists
        - Updating the anonymous accounts only role role with the previously
        defined content selector privileges

    Args:
        args: Command line arguments
    """
    actions.check_package_files(args)

    nexus_api = NexusAPI(
        password=args.admin_password,
        nexus_host=args.nexus_host,
        nexus_port=args.nexus_port,
        nexus_path=args.nexus_path,
    )

    # Parse allowlists
    pypi_allowlist, cran_allowlist, apt_allowlist = actions.get_allowlists(
        args.pypi_package_file, args.cran_package_file, args.apt_package_file
    )

    # Recreate all content selectors and associated privileges according to the
    # allowlists
    privileges = actions.recreate_privileges(
        args.packages, nexus_api, pypi_allowlist, cran_allowlist, apt_allowlist
    )

    # Grant privileges to the nexus allowlist role
    nexus_api.update_role(
        name=_ROLE_NAME,
        description="allows access to selected packages",
        privileges=privileges,
    )
