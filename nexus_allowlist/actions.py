import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus_allowlist.nexus import NexusAPI, RepositoryType


@dataclass
class Repository:
    repo_type: RepositoryType
    name: str
    remote_url: str


def get_nexus_repositories(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "pypi_proxy": Repository(
            repo_type=RepositoryType.PYPI,
            name="pypi-proxy",
            remote_url="https://pypi.org",
        ),
        "cran_proxy": Repository(
            repo_type=RepositoryType.CRAN,
            name="cran-proxy",
            remote_url="https://cran.r-project.org",
        ),
        "apt_proxy": Repository(
            repo_type=RepositoryType.APT,
            name="apt-proxy",
            remote_url=args.apt_repository_url,
        ),
    }


def check_package_files(args: argparse.Namespace) -> None:
    """
    Ensure that the allowlist files exist

    Args:
        args: Command line arguments

    raise:
        Exception: if any declared allowlist file does not exist
    """
    for package_file in [
        args.pypi_package_file,
        args.cran_package_file,
        args.apt_package_file,
    ]:
        if package_file and not package_file.is_file():
            msg = f"Package allowlist file {package_file} does not exist"
            raise Exception(msg)


def get_allowlists(
    pypi_package_file: Path, cran_package_file: Path, apt_package_file: Path
) -> tuple[list[str], list[str], list[str]]:
    """
    Create allowlists for PyPI, CRAN and APT packages

    Args:
        pypi_package_file: Path to the PyPI allowlist file or None
        cran_package_file: Path to the CRAN allowlist file or None

    Returns:
        A tuple of the PyPI, CRAN and APT allowlists (in that order). The lists are
        [] if the corresponding package file argument was None
    """
    pypi_allowlist = []
    cran_allowlist = []
    apt_allowlist = []

    if pypi_package_file:
        pypi_allowlist = get_allowlist(pypi_package_file, repo_type=RepositoryType.PYPI)

    if cran_package_file:
        cran_allowlist = get_allowlist(cran_package_file, repo_type=RepositoryType.CRAN)

    if apt_package_file:
        apt_allowlist = get_allowlist(apt_package_file, repo_type=RepositoryType.APT)

    return (pypi_allowlist, cran_allowlist, apt_allowlist)


def get_allowlist(allowlist_path: Path, repo_type: RepositoryType) -> list[str]:
    """
    Read list of allowed packages from a file

    Args:
        allowlist_path: Path to the allowlist file
        repo_type: The type of repository the allowlist applies to

    Returns:
        List of the package names specified in the file
    """
    allowlist = []
    with open(allowlist_path) as allowlist_file:
        # Sanitise package names
        # - convert to lower case if the package is on PyPI or APT. Leave alone on CRAN
        #   to prevent issues with case-sensitivity - for PyPI replace strings of '.',
        #   '_' or '-' with '-'
        #   https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/#name
        # - remove any blank entries, which act as a wildcard that would allow any
        #   package
        pypi_replace_characters = re.compile(r"[\._-]+")
        for package_name in allowlist_file.readlines():
            match repo_type:
                case RepositoryType.CRAN:
                    package_name_parsed = package_name.strip()
                case RepositoryType.APT:
                    package_name_parsed = package_name.lower().strip()
                case RepositoryType.PYPI:
                    package_name_parsed = pypi_replace_characters.sub(
                        "-", package_name.lower().strip()
                    )
            allowlist.append(package_name_parsed)
    return allowlist


def recreate_repositories(
    nexus_api: NexusAPI,
    nexus_repositories: dict[str, Any]
) -> None:
    """
    Create PyPI, CRAN and APT proxy repositories in an idempotent manner

    Args:
        nexus_api: NexusAPI object
        nexus_repositories: A dict of Repository objects
    """
    # Delete all existing repositories
    nexus_api.delete_all_repositories()

    for repository in nexus_repositories.values():
        nexus_api.create_proxy_repository(
            repo_type=repository.repo_type,
            name=repository.name,
            remote_url=repository.remote_url,
        )


def recreate_privileges(
    packages: str,
    nexus_api: NexusAPI,
    nexus_repositories: dict[str, Any],
    pypi_allowlist: list[str],
    cran_allowlist: list[str],
    apt_allowlist: list[str],
    apt_release: str,
    apt_archives: list[str],
) -> list[str]:
    """
    Create content selectors and content selector privileges based on the
    package setting and allowlists in an idempotent manner

    Args:
        nexus_api: NexusAPI object
        nexus_repositories: A dict of Repository objects
        pypi_allowlist: List of allowed PyPI packages
        cran_allowlist: List of allowed CRAN packages
        apt_allowlist: List of allowed APT packages
        apt_release: The APT release
        apt_archives: List of allowed APT archives

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
    apt_privilege_names = []

    # Content selector and privilege for PyPI 'simple' path, used to search for
    # packages
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="simple",
        description="Allow access to 'simple' directory in PyPI repository",
        expression='format == "pypi" and path=^"/simple"',
        repo_type=nexus_repositories["pypi_proxy"].repo_type,
        repo=nexus_repositories["pypi_proxy"].name,
    )
    pypi_privilege_names.append(privilege_name)

    # Content selector and privilege for CRAN 'PACKAGES' file which contains an
    # index of all packages
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="packages",
        description="Allow access to 'PACKAGES' file in CRAN repository",
        expression='format == "r" and path=="/src/contrib/PACKAGES"',
        repo_type=nexus_repositories["cran_proxy"].repo_type,
        repo=nexus_repositories["cran_proxy"].name,
    )
    cran_privilege_names.append(privilege_name)

    # Content selector and privilege for CRAN 'archive.rds' file which contains an
    # metadata for all archived packages
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="archive",
        description="Allow access to 'archive.rds' file in CRAN repository",
        expression='format == "r" and path=="/src/contrib/Meta/archive.rds"',
        repo_type=nexus_repositories["cran_proxy"].repo_type,
        repo=nexus_repositories["cran_proxy"].name,
    )
    cran_privilege_names.append(privilege_name)

    # Content selector and privilege for APT 'Packages.gz' file which contains an
    # metadata for all archived packages
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="apt-packages",
        description="Allow access to 'Packages.gz' file in APT repository",
        expression=f'format == "apt" and path=~"^/dists/{apt_release}/.*/Packages.gz"',
        repo_type=nexus_repositories["apt_proxy"].repo_type,
        repo=nexus_repositories["apt_proxy"].name,
    )
    apt_privilege_names.append(privilege_name)

    # Content selector and privilege for APT 'InRelease' file which contains an
    # metadata about the APT distribution
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="inrelease",
        description="Allow access to 'InRelease' file in APT repository",
        expression=f'format == "apt" and path=="/dists/{apt_release}/InRelease"',
        repo_type=nexus_repositories["apt_proxy"].repo_type,
        repo=nexus_repositories["apt_proxy"].name,
    )
    apt_privilege_names.append(privilege_name)

    # Content selector and privilege for APT 'Translation-*' files which contains an
    # metadata about the APT distribution
    privilege_name = create_content_selector_and_privilege(
        nexus_api,
        name="apt-translation",
        description="Allow access to 'Translation-*' file in APT repository",
        expression=(
            f'format == "apt" and path=~"^/dists/{apt_release}/.*/Translation-.*"'
        ),
        repo_type=nexus_repositories["apt_proxy"].repo_type,
        repo=nexus_repositories["apt_proxy"].name,
    )
    apt_privilege_names.append(privilege_name)

    # Create content selectors and privileges for packages according to the
    # package setting
    if packages == "all":
        # Allow all PyPI packages
        privilege_name = create_content_selector_and_privilege(
            nexus_api,
            name="pypi-all",
            description="Allow access to all PyPI packages",
            expression='format == "pypi" and path=^"/packages/"',
            repo_type=nexus_repositories["pypi_proxy"].repo_type,
            repo=nexus_repositories["pypi_proxy"].name,
        )
        pypi_privilege_names.append(privilege_name)

        # Allow all CRAN packages
        privilege_name = create_content_selector_and_privilege(
            nexus_api,
            name="cran-all",
            description="Allow access to all CRAN packages",
            expression='format == "r" and path=^"/src/contrib"',
            repo_type=nexus_repositories["cran_proxy"].repo_type,
            repo=nexus_repositories["cran_proxy"].name,
        )
        cran_privilege_names.append(privilege_name)

        # Allow all APT packages
        privilege_name = create_content_selector_and_privilege(
            nexus_api,
            name="apt-all",
            description="Allow access to all APT packages",
            expression=(
                f'format == "apt" and path=~"^/pool/({'|'.join(apt_archives)})/.*"'
            ),
            repo_type=nexus_repositories["apt_proxy"].repo_type,
            repo=nexus_repositories["apt_proxy"].name,
        )
        apt_privilege_names.append(privilege_name)
    elif packages == "selected":
        # Allow selected PyPI packages
        for package in pypi_allowlist:
            privilege_name = create_content_selector_and_privilege(
                nexus_api,
                name=f"pypi-{package}",
                description=f"Allow access to {package} on PyPI",
                expression=f'format == "pypi" and path=^"/packages/{package}/"',
                repo_type=nexus_repositories["pypi_proxy"].repo_type,
                repo=nexus_repositories["pypi_proxy"].name,
            )
            pypi_privilege_names.append(privilege_name)

        # Allow selected CRAN packages
        for package in cran_allowlist:
            privilege_name = create_content_selector_and_privilege(
                nexus_api,
                name=f"cran-{package}",
                description=f"allow access to {package} on CRAN",
                expression=(
                    'format == "r" '
                    f'and (path=^"/src/contrib/{package}_" '
                    f'or path=^"/src/contrib/Archive/{package}/{package}_")'
                ),
                repo_type=nexus_repositories["cran_proxy"].repo_type,
                repo=nexus_repositories["cran_proxy"].name,
            )
            cran_privilege_names.append(privilege_name)

        # Allow selected APT packages
        for package in apt_allowlist:
            privilege_name = create_content_selector_and_privilege(
                nexus_api,
                name=f"apt-{package}",
                description=f"Allow access to {packages} APT package",
                expression=(
                    'format == "apt" and '
                    f'path=~"^/pool/({'|'.join(apt_archives)})/.*/{package}.*"'
                ),
                repo_type=nexus_repositories["apt_proxy"].repo_type,
                repo=nexus_repositories["apt_proxy"].name,
            )
            apt_privilege_names.append(privilege_name)

    return pypi_privilege_names + cran_privilege_names + apt_privilege_names


def create_content_selector_and_privilege(
    nexus_api: NexusAPI,
    name: str,
    description: str,
    expression: str,
    repo_type: RepositoryType,
    repo: str,
) -> str:
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
