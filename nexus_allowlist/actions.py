import re

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
