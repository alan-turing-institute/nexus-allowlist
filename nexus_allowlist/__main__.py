#! /usr/bin/env python3
import logging
import re
import sys
from argparse import ArgumentParser
from pathlib import Path

from nexus_allowlist.exceptions import InitialPasswordError
from nexus_allowlist.nexus import NexusAPI

logging.basicConfig(
    format="{asctime} {levelname}:{message}",
    style="{",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    level=logging.INFO,
)

_NEXUS_REPOSITORIES = {
    "pypi_proxy": {
        "repo_type": "pypi",
        "name": "pypi-proxy",
        "remote_url": "https://pypi.org/",
    },
    "cran_proxy": {
        "repo_type": "r",
        "name": "cran-proxy",
        "remote_url": "https://cran.r-project.org/",
    },
}

_ROLE_NAME = "nexus user"


def main():
    parser = ArgumentParser(description="Enforce allowlists for Nexus3")
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

    # Group of arguments for packages
    packages_parser = ArgumentParser(add_help=False)
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


def change_initial_password(args):
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
    )

    nexus_api.change_admin_password(args.admin_password)


def test_authentiation(args):
    nexus_api = NexusAPI(
        password=args.admin_password,
        nexus_host=args.nexus_host,
        nexus_port=args.nexus_port,
    )

    if not nexus_api.test_auth():
        sys.exit(1)


def initial_configuration(args):
    """
    Fully configure Nexus in an idempotent manner.

    This includes:
        - Deleting all respositories
        - Creating CRAN and PyPI proxies
        - Deleting all content selectors and content selector privileges
        - Creating content selectors and content selector privileges according
          to the package setting and allowlists
        - Deleting all non-default roles
        - Creating a role with the previously defined content selector
          privileges
        - Giving anonymous users ONLY the previously defined role
        - Enabling anonymous access

    Args:
        args: Command line arguments
    """
    check_package_files(args)

    nexus_api = NexusAPI(
        password=args.admin_password,
        nexus_host=args.nexus_host,
        nexus_port=args.nexus_port,
    )

    # Ensure only desired repositories exist
    recreate_repositories(nexus_api)

    pypi_allowlist, cran_allowlist = get_allowlists(
        args.pypi_package_file, args.cran_package_file
    )
    privileges = recreate_privileges(
        args.packages, nexus_api, pypi_allowlist, cran_allowlist
    )

    # Delete non-default roles
    nexus_api.delete_all_custom_roles()

    # Create a role
    nexus_api.create_role(
        name=_ROLE_NAME,
        description="allows access to selected packages",
        privileges=privileges,
    )

    # Update anonymous users roles
    nexus_api.update_anonymous_user_roles([_ROLE_NAME])

    # Enable anonymous access
    nexus_api.enable_anonymous_access()


def update_allow_lists(args):
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
    check_package_files(args)

    nexus_api = NexusAPI(
        password=args.admin_password,
        nexus_host=args.nexus_host,
        nexus_port=args.nexus_port,
    )

    pypi_allowlist, cran_allowlist = get_allowlists(
        args.pypi_package_file, args.cran_package_file
    )
    privileges = recreate_privileges(
        args.packages, nexus_api, pypi_allowlist, cran_allowlist
    )

    # Update role
    nexus_api.update_role(
        name=_ROLE_NAME,
        description="allows access to selected packages",
        privileges=privileges,
    )


def check_package_files(args):
    """
    Ensure that the allowlist files exist

    Args:
        args: Command line arguments

    raise:
        Exception: if any declared allowlist file does not exist
    """
    for package_file in [args.pypi_package_file, args.cran_package_file]:
        if package_file and not package_file.is_file():
            msg = f"Package allowlist file {package_file} does not exist"
            raise Exception(msg)


def get_allowlists(pypi_package_file, cran_package_file):
    """
    Create allowlists for PyPI and CRAN packages

    Args:
        pypi_package_file: Path to the PyPI allowlist file or None
        cran_package_file: Path to the CRAN allowlist file or None

    Returns:
        A tuple of the PyPI and CRAN allowlists (in that order). The lists are
        [] if the corresponding package file argument was None
    """
    pypi_allowlist = []
    cran_allowlist = []

    if pypi_package_file:
        pypi_allowlist = get_allowlist(pypi_package_file, False)

    if cran_package_file:
        cran_allowlist = get_allowlist(cran_package_file, True)

    return (pypi_allowlist, cran_allowlist)


def get_allowlist(allowlist_path, is_cran):
    """
    Read list of allowed packages from a file

    Args:
        allowlist_path: Path to the allowlist file
        is_cran: True if the allowlist if for CRAN, False if it is for PyPI

    Returns:
        List of the package names specified in the file
    """
    allowlist = []
    with open(allowlist_path) as allowlist_file:
        # Sanitise package names
        # - convert to lower case if the package is on PyPI. Leave alone on CRAN to
        #   prevent issues with case-sensitivity - for PyPI replace strings of '.', '_'
        #   or '-' with '-'
        #   https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/#name
        # - remove any blank entries, which act as a wildcard that would allow any
        #   package
        pypi_replace_characters = re.compile(r"[\._-]+")
        for package_name in allowlist_file.readlines():
            if is_cran:
                package_name_parsed = package_name.strip()
            else:
                package_name_parsed = pypi_replace_characters.sub(
                    "-", package_name.lower().strip()
                )
            allowlist.append(package_name_parsed)
    return allowlist


def recreate_repositories(nexus_api):
    """
    Create PyPI and CRAN proxy repositories in an idempotent manner

    Args:
        nexus_api: NexusAPI object
    """
    # Delete all existing repositories
    nexus_api.delete_all_repositories()

    for repository in _NEXUS_REPOSITORIES.values():
        nexus_api.create_proxy_repository(**repository)


def recreate_privileges(packages, nexus_api, pypi_allowlist, cran_allowlist):
    """
    Create content selectors and content selector privileges based on the
    package setting and allowlists in an idempotent manner

    Args:
        nexus_api: NexusAPI object
        pypi_allowlist: List of allowed PyPI packages
        cran_allowlist: List of allowed CRAN packages

    Returns:
        List of the names of all content selector privileges
    """
    # Delete all existing content selector privileges
    # These must be deleted before the content selectors as the content selectors
    # as the privileges depend on the content selectors
    nexus_api.delete_all_content_selector_privileges()

    # Delete all existing content selectors
    nexus_api.delete_all_content_selectors()

    pypi_privilege_names = []
    cran_privilege_names = []

    # Content selector and privilege for PyPI 'simple' path, used to search for
    # packages
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="simple",
        description="Allow access to 'simple' directory in PyPI repository",
        expression='format == "pypi" and path=^"/simple"',
        repo_type=_NEXUS_REPOSITORIES["pypi_proxy"]["repo_type"],
        repo=_NEXUS_REPOSITORIES["pypi_proxy"]["name"],
    )
    pypi_privilege_names.append(privilege_name)

    # Content selector and privilege for CRAN 'PACKAGES' file which contains an
    # index of all packages
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="packages",
        description="Allow access to 'PACKAGES' file in CRAN repository",
        expression='format == "r" and path=="/src/contrib/PACKAGES"',
        repo_type=_NEXUS_REPOSITORIES["cran_proxy"]["repo_type"],
        repo=_NEXUS_REPOSITORIES["cran_proxy"]["name"],
    )
    cran_privilege_names.append(privilege_name)

    # Create content selectors and privileges for packages according to the
    # package setting
    if packages == "all":
        # Allow all PyPI packages
        privilege_name = create_content_selector_and_privilege(
            nexus_api,
            name="pypi-all",
            description="Allow access to all PyPI packages",
            expression='format == "pypi" and path=^"/packages/"',
            repo_type=_NEXUS_REPOSITORIES["pypi_proxy"]["repo_type"],
            repo=_NEXUS_REPOSITORIES["pypi_proxy"]["name"],
        )
        pypi_privilege_names.append(privilege_name)

        # Allow all CRAN packages
        privilege_name = create_content_selector_and_privilege(
            nexus_api,
            name="cran-all",
            description="Allow access to all CRAN packages",
            expression='format == "r" and path=^"/src/contrib"',
            repo_type=_NEXUS_REPOSITORIES["cran_proxy"]["repo_type"],
            repo=_NEXUS_REPOSITORIES["cran_proxy"]["name"],
        )
        cran_privilege_names.append(privilege_name)
    elif packages == "selected":
        # Allow selected PyPI packages
        for package in pypi_allowlist:
            privilege_name = create_content_selector_and_privilege(
                nexus_api,
                name=f"pypi-{package}",
                description=f"Allow access to {package} on PyPI",
                expression=f'format == "pypi" and path=^"/packages/{package}/"',
                repo_type=_NEXUS_REPOSITORIES["pypi_proxy"]["repo_type"],
                repo=_NEXUS_REPOSITORIES["pypi_proxy"]["name"],
            )
            pypi_privilege_names.append(privilege_name)

        # Allow selected CRAN packages
        for package in cran_allowlist:
            privilege_name = create_content_selector_and_privilege(
                nexus_api,
                name=f"cran-{package}",
                description=f"allow access to {package} on CRAN",
                expression=f'format == "r" and path=^"/src/contrib/{package}_"',
                repo_type=_NEXUS_REPOSITORIES["cran_proxy"]["repo_type"],
                repo=_NEXUS_REPOSITORIES["cran_proxy"]["name"],
            )
            cran_privilege_names.append(privilege_name)

    return pypi_privilege_names + cran_privilege_names


def create_content_selector_and_privilege(
    nexus_api, name, description, expression, repo_type, repo
):
    """
    Create a content selector and corresponding content selector privilege

    Args:
        nexus_api: NexusAPI object
        name: Name shared by the content selector and content selector
            privilege
        description: Description shared by the content selector and content
            selector privilege
        expression: CSEL expression defining the content selector
        repo_type: Type of repository the content selector privilege applies to
        repo: Name of the repository the content selector privilege applies to
    """
    nexus_api.create_content_selector(
        name=name, description=description, expression=expression
    )

    nexus_api.create_content_selector_privilege(
        name=name,
        description=description,
        repo_type=repo_type,
        repo=repo,
        content_selector=name,
    )

    return name


if __name__ == "__main__":
    main()
