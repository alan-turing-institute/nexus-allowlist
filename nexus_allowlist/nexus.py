import logging
from enum import Enum

import requests

from nexus_allowlist.exceptions import RepositoryTypeError

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