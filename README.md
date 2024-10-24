# Nexus Allowlist
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-1-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

A package for configuring [Sonatype Nexus Repository Manager OSS](https://github.com/sonatype/nexus-public) to only allow selected packages to be installed from proxy repositories.

Supports creating CRAN and PyPI proxies which allow either all, or only named packages.

## Docker

A [Dockerfile](Dockerfile) and example [docker compose](docker-compose.yaml) configuration demonstrate how to use the script in conjunction with a Nexus OSS container.

## Instructions

### Test deployment

Check and, if you would like, change the following environment variables for the Nexus Allowlist container in [`docker-compose.yaml`](./docker-compose.yaml).

| Environment variable   | meaning                                                                                                                                          |
| ---------------------- | -------------------------------------------------------------------------------------------------------------                                    |
| NEXUS_ADMIN_PASSWORD   | Password for the Nexus OSS admin user (changes from the default on first rune then used for authentication)                                      |
| NEXUS_PACKAGES         | Whether to allow all packages or only selected packages [`all`, `selected`]                                                                      |
| NEXUS_HOST             | Hostname of Nexus OSS host                                                                                                                       |
| NEXUS_PORT             | Port of Nexus OSS                                                                                                                                |
| NEXUS_PATH             | [Context path](https://help.sonatype.com/en/configuring-the-runtime-environment.html#changing-the-context-path) of Nexus OSS. Only used if the Nexus is hosted behind a reverse proxy with a URL like `https://your_url.domain/nexus/`. If not defined, the base URI remains `/`.                                                                                                                              |
| ENTR_FALLBACK          | If defined, don't use `entr` to check for allowlist updates (this will be less reactive but we have found `entr` to not work in some situations) |

Example allowlist files are included in the repository for [PyPI](allowlists/pypi.allowlist) and [CRAN](allowlists/cran.allowlist).
The PyPI allowlist includes numpy, pandas, matplotlib and their dependencies.
The CRAN allowlist includes cli and data.table
You can add more packages by writing the package names, one per line, in the allowlist files.

Start the Nexus and Nexus Allowlist containers using docker compose

```
docker compose up -d
```

You can monitor the Nexus Allowlist container instance

```
docker compose logs -f allowlist
```

### How it works

The container [command](entrypoint.sh)

1. Ensures that allowlist files `/allowlists/pypi.allowlist` and `/allowlists/cran.allowlist` exist
1. Waits for Nexus OSS to be available at `NEXUS_HOST:NEXUS_PORT`
1. If the Nexus OSS initial password file is present (at `/nexus-data/admin.password`)
  1. Changes the admin password to `NEXUS_ADMIN_PASSWORD`
  1. Runs initial configuration (creates a role, repositories, content selectors, _etc._)
1. Reruns the content selector configuration (which enforces the allowlists) every time either of the allowlist files are modified

[Caddy](https://caddyserver.com/) acts as a reverse proxy, passing requests to the Nexus OSS server.
The [configuration file](Caddyfile) replaces [401](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401) responses from Nexus OSS with [403](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403) so that pip does not prompt a user for authentication when attempting to install a blocked package.

### Usage

#### Pip

You can edit `~/.config/pip/pip.conf` to use the Nexus PyPI proxy.
To apply globally edit `/etc/pip.conf`.
For example

```
[global]
index = http://localhost:8080/repository/pypi-proxy/pypi
index-url = http://localhost:8080/repository/pypi-proxy/simple
```

You should now only be able to install packages from the allowlist.
For example,

- `pip install numpy` should succeed
- `pip install mkdocs` should fail

#### R

You can edit `~/.Rprofile`to use the Nexus CRAN proxy.
To apply globally edit `/etc/R/Rprofile.site`.
For example

```
local({
    r <- getOption("repos")
    r["CRAN"] <- "http://localhost:8080/repository/cran-proxy"
    options(repos=r)
})
```
You should now only be able to install packages from the allowlist.
For example,

- `install.packages("data.table")` should succeed
- `install.packages("ggplot2")` should fail

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/JimMadge"><img src="https://avatars.githubusercontent.com/u/23616154?v=4?s=100" width="100px;" alt="Jim Madge"/><br /><sub><b>Jim Madge</b></sub></a><br /><a href="https://github.com/The contributors/nexus-allowlist/issues?q=author%3AJimMadge" title="Bug reports">🐛</a> <a href="https://github.com/The contributors/nexus-allowlist/commits?author=JimMadge" title="Code">💻</a> <a href="https://github.com/The contributors/nexus-allowlist/commits?author=JimMadge" title="Documentation">📖</a> <a href="#ideas-JimMadge" title="Ideas, Planning, & Feedback">🤔</a> <a href="#infra-JimMadge" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="https://github.com/The contributors/nexus-allowlist/pulls?q=is%3Apr+reviewed-by%3AJimMadge" title="Reviewed Pull Requests">👀</a> <a href="https://github.com/The contributors/nexus-allowlist/commits?author=JimMadge" title="Tests">⚠️</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!