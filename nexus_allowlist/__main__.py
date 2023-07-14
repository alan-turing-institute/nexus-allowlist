#! /usr/bin/env python3
import logging
import re
import sys
from argparse import ArgumentParser
from enum import Enum
from pathlib import Path

import requests

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

_REQUEST_TIMEOUT = 10


class ResponseCode(Enum):
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_SERVER_ERROR = 500


class InitialPasswordError(Exception):
    pass


class RepositoryTypeError(Exception):
    pass


class NexusAPI:
    """Interface to the Nexus REST API"""

    def __init__(self, *, password, username="admin", nexus_host, nexus_port):
        self.nexus_api_root = f"http://{nexus_host}:{nexus_port}/service/rest"
        self.username = username
        self.password = password

    @property
    def auth(self):
        return requests.auth.HTTPBasicAuth(self.username, self.password)

    def change_admin_password(self, new_password):
        """
        Change the password of the 'admin' account

        Args:
            new_password: New password to be set
        """
        logging.info(f"Old password: {self.password}")
        logging.info(f"New password: {new_password}")
        response = requests.put(
            f"{self.nexus_api_root}/v1/security/users/admin/change-password",
            auth=self.auth,
            headers={"content-type": "text/plain"},
            data=new_password,
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code == ResponseCode.NO_CONTENT:
            logging.info("Changed admin password")
            self.password = new_password
        else:
            logging.error("Changing password failed")
            logging.error(response.content)

    def delete_all_repositories(self):
        """Delete all existing repositories"""
        response = requests.get(
            f"{self.nexus_api_root}/v1/repositories",
            auth=self.auth,
            timeout=_REQUEST_TIMEOUT,
        )
        repositories = response.json()

        for repo in repositories:
            name = repo["name"]
            logging.info(f"Deleting repository: {name}")
            response = requests.delete(
                f"{self.nexus_api_root}/v1/repositories/{name}",
                auth=self.auth,
                timeout=_REQUEST_TIMEOUT,
            )
            code = response.status_code
            if code == ResponseCode.NO_CONTENT:
                logging.info("Repository successfully deleted")
            else:
                logging.error(f"Repository deletion failed.\nStatus code:{code}")
                logging.error(response.content)

    def create_proxy_repository(self, repo_type, name, remote_url):
        """
        Create a proxy repository. Currently supports PyPI and R formats

        Args:
            repo_type: Type of repository, one of 'pypi' or 'r'
            name: Name of the repository
            remote_url: Path of the repository to proxy
        """
        valid_types = ["pypi", "r"]
        if repo_type not in valid_types:
            msg = f"repo_type should be one of {valid_types}, got: {repo_type}"
            raise RepositoryTypeError(msg)

        payload = {
            "name": "",
            "online": True,
            "storage": {
                "blobStoreName": "default",
                "strictContentTypeValidation": True,
            },
            "proxy": {
                "remoteUrl": "",
                "contentMaxAge": 1440,
                "metadataMaxAge": 1440,
            },
            "negativeCache": {"enabled": True, "timeToLive": 1440},
            "httpClient": {
                "blocked": False,
                "autoBlock": True,
            },
        }
        payload["name"] = name
        payload["proxy"]["remoteUrl"] = remote_url

        logging.info(f"Creating {repo_type} repository: {name}")
        response = requests.post(
            f"{self.nexus_api_root}/v1/repositories/{repo_type}/proxy",
            auth=self.auth,
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.CREATED:
            logging.info(f"{repo_type} proxy successfully created")
        else:
            logging.error(f"{repo_type} proxy creation failed.\nStatus code: {code}")
            logging.error(response.content)

    def delete_all_content_selectors(self):
        """Delete all existing content selectors"""
        response = requests.get(
            f"{self.nexus_api_root}/v1/security/content-selectors",
            auth=self.auth,
            timeout=_REQUEST_TIMEOUT,
        )
        content_selectors = response.json()

        for content_selector in content_selectors:
            name = content_selector["name"]
            logging.info(f"Deleting content selector: {name}")
            response = requests.delete(
                f"{self.nexus_api_root}/v1/security/content-selectors/{name}",
                auth=self.auth,
                timeout=_REQUEST_TIMEOUT,
            )
            code = response.status_code
            if code == ResponseCode.NO_CONTENT:
                logging.info("Content selector successfully deleted")
            else:
                logging.error(f"Content selector deletion failed.\nStatus code:{code}")
                logging.error(response.content)

    def create_content_selector(self, name, description, expression):
        """
        Create a new content selector

        Args:
            name: Name of the content selector
            description: Description of the content selector
            expression: CSEL query (https://help.sonatype.com/repomanager3/nexus-repository-administration/access-control/content-selectors)
                to identify content
        """
        payload = {
            "name": f"{name}",
            "description": f"{description}",
            "expression": f"{expression}",
        }

        logging.info(f"Creating content selector: {name}")
        response = requests.post(
            f"{self.nexus_api_root}/v1/security/content-selectors",
            auth=self.auth,
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.NO_CONTENT:
            logging.info("content selector successfully created")
        elif code == ResponseCode.INTERNAL_SERVER_ERROR:
            logging.warning("content selector already exists")
        else:
            logging.error(f"content selector creation failed.\nStatus code: {code}")
            logging.error(response.content)

    def delete_all_content_selector_privileges(self):
        """Delete all existing content selector privileges"""
        response = requests.get(
            f"{self.nexus_api_root}/v1/security/privileges",
            auth=self.auth,
            timeout=_REQUEST_TIMEOUT,
        )
        privileges = response.json()

        for privilege in privileges:
            if privilege["type"] != "repository-content-selector":
                continue

            name = privilege["name"]
            logging.info(f"Deleting content selector privilege: {name}")
            response = requests.delete(
                f"{self.nexus_api_root}/v1/security/privileges/{name}",
                auth=self.auth,
                timeout=_REQUEST_TIMEOUT,
            )
            code = response.status_code
            if code == ResponseCode.NO_CONTENT:
                logging.info(f"Content selector privilege: {name} successfully deleted")
            else:
                logging.error(
                    f"Content selector privilege deletion failed. Status code:{code}"
                )
                logging.error(response.content)

    def create_content_selector_privilege(
        self, name, description, repo_type, repo, content_selector
    ):
        """
        Create a new content selector privilege

        Args:
            name: Name of the content selector privilege
            description: Description of the content selector privilege
            repo_type: Type of repository this privilege applies to
            repo: Name of the repository this privilege applies to
            content_selector: Name of the content selector applied to this
                privilege
        """
        payload = {
            "name": f"{name}",
            "description": f"{description}",
            "actions": ["READ"],
            "format": f"{repo_type}",
            "repository": f"{repo}",
            "contentSelector": f"{content_selector}",
        }

        logging.info(f"Creating content selector privilege: {name}")
        response = requests.post(
            (
                f"{self.nexus_api_root}/v1/security/privileges"
                "/repository-content-selector"
            ),
            auth=self.auth,
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.CREATED:
            logging.info(f"content selector privilege {name} successfully created")
        elif code == ResponseCode.BAD_REQUEST:
            logging.warning(f"content selector privilege {name} already exists")
        else:
            logging.error(
                f"content selector privilege {name} creation failed."
                f" Status code: {code}"
            )
            logging.error(response.content)

    def delete_all_custom_roles(self):
        """Delete all roles except for the default 'nx-admin' and 'nxanonymous'"""
        response = requests.get(
            f"{self.nexus_api_root}/v1/security/roles",
            auth=self.auth,
            timeout=_REQUEST_TIMEOUT,
        )
        roles = response.json()

        for role in roles:
            name = role["name"]
            if name in ["nx-admin", "nx-anonymous"]:
                continue

            logging.info(f"Deleting role: {name}")
            response = requests.delete(
                f"{self.nexus_api_root}/v1/security/roles/{name}",
                auth=self.auth,
                timeout=_REQUEST_TIMEOUT,
            )
            code = response.status_code
            if code == ResponseCode.NO_CONTENT:
                logging.info("Role successfully deleted")
            else:
                logging.error(f"Role deletion failed.\nStatus code:{code}")
                logging.error(response.content)

    def create_role(self, name, description, privileges, roles):
        """
        Create a new role

        Args:
            name: Name of the role (also becomes the role id)
            description: Description of the role
            privileges: Privileges to be granted to the role
            roles: Roles to be granted to the role
        """
        payload = {
            "id": f"{name}",
            "name": f"{name}",
            "description": f"{description}",
            "privileges": privileges,
            "roles": roles,
        }

        logging.info(f"Creating role: {name}")
        response = requests.post(
            (f"{self.nexus_api_root}/v1/security/roles"),
            auth=self.auth,
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.OK:
            logging.info(f"role {name} successfully created")
        elif code == ResponseCode.BAD_REQUEST:
            logging.warning(f"role {name} already exists")
        else:
            logging.error(f"role {name} creation failed.\nStatus code: {code}")
            logging.error(response.content)

    def update_role(self, name, description, privileges, roles):
        """
        Update an existing role

        Args:
            name: Name of the role (also assumed to be the role id)
            description: Description of the role
            privileges: Privileges to be granted to the role (overwrites all
                existing privileges)
            roles: Roles to be granted to the role (overwrites all existing
                roles)
        """
        payload = {
            "id": f"{name}",
            "name": f"{name}",
            "description": f"{description}",
            "privileges": privileges,
            "roles": roles,
        }

        logging.info(f"updating role: {name}")
        response = requests.put(
            (f"{self.nexus_api_root}/v1/security/roles/{name}"),
            auth=self.auth,
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.NO_CONTENT:
            logging.info(f"role {name} successfully created")
        elif code == ResponseCode.NOT_FOUND:
            logging.warning(f"role {name} does not exist")
        else:
            logging.error(f"role {name} update failed.\nStatus code: {code}")
            logging.error(response.content)

    def enable_anonymous_access(self):
        """Enable access from anonymous users (where no credentials are supplied)"""
        response = requests.put(
            f"{self.nexus_api_root}/v1/security/anonymous",
            auth=self.auth,
            json={
                "enabled": True,
                "userId": "anonymous",
                "realName": "Local Authorizing Realm",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.OK:
            logging.info("Anonymous access enabled")
        else:
            logging.error(f"Enabling anonymous access failed.\nStatus code: {code}")
            logging.error(response.content)

    def update_anonymous_user_roles(self, roles):
        """
        Update the roles assigned to the 'anonymous' user

        Args:
            roles: Roles to be assigned to the anonymous user, overwrites all
                existing roles
        """
        # Get existing user data JSON
        response = requests.get(
            f"{self.nexus_api_root}/v1/security/users",
            auth=self.auth,
            timeout=_REQUEST_TIMEOUT,
        )
        users = response.json()
        for user in users:
            if user["userId"] == "anonymous":
                anonymous_user = user
                break

        # Change roles
        anonymous_user["roles"] = roles

        # Push changes to Nexus
        response = requests.put(
            f"{self.nexus_api_root}/v1/security/users/{anonymous_user['userId']}",
            auth=self.auth,
            json=anonymous_user,
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.NO_CONTENT:
            logging.info(f"User {anonymous_user['userId']} roles updated")
        else:
            logging.error(
                f"User {anonymous_user['userId']} role update failed."
                f"\nStatus code: {code}"
            )
            logging.error(response.content)

    def test_auth(self):
        """Use list users endpoint to test authentication"""
        response = requests.get(
            f"{self.nexus_api_root}/v1/security/users",
            auth=self.auth,
            params={"userId": "admin"},
            timeout=_REQUEST_TIMEOUT,
        )
        code = response.status_code
        if code == ResponseCode.OK:
            logging.info("API Authentication test passed")
            return True
        elif code in [ResponseCode.UNAUTHORIZED, ResponseCode.FORBIDDEN]:
            logging.error("API Authentication test failed")
            return False
        else:
            logging.error(f"API Authentication test inconclusive.\nStatus code:{code}")
            logging.error(response.content)
            return False


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