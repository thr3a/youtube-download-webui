# builder-examples.md

# Builder examples

## Using remote builder for single-arch

If you're developing on ARM64 (like Apple Silicon), but you want to deploy on AMD64 (x86 64-bit), by default, Kamal will set up a local buildx configuration that does this through QEMU emulation. However, this can be quite slow, especially on the first build.

If you want to speed up this process by using a remote AMD64 host to natively build the AMD64 part of the image, you can set a remote builder:

```yaml
builder:
  arch: amd64
  remote: ssh://root@192.168.0.1
```

Kamal will use the remote to build when deploying from an ARM64 machine, or build locally when deploying from an AMD64 machine.

**Note:** You must have Docker running on the remote host being used as a builder. This instance should only be shared for builds using the same registry and credentials.

## Using remote builder for multi-arch

You can also build a multi-arch image. If a remote is set, Kamal will build the architecture matching your deployment server locally and the other architecture remotely.

So if you're developing on ARM64 (like Apple Silicon), it will build the ARM64 architecture locally and the AMD64 architecture remotely.

```yaml
builder:
  arch:
    - amd64
    - arm64
  remote: ssh://root@192.168.0.1
```

## Using local builder for single-arch

If you always want to build locally for a single architecture, Kamal will build the image using a local buildx instance.

```yaml
builder:
  arch: amd64
```

## Using a different Dockerfile or context when building

If you need to pass a different Dockerfile or context to the build command (e.g., if you're using a monorepo or you have different Dockerfiles), you can do so in the builder options:

```yaml
# Use a different Dockerfile
builder:
  dockerfile: Dockerfile.xyz

# Set context
builder:
  context: ".."

# Set Dockerfile and context
builder:
  dockerfile: "../Dockerfile.xyz"
  context: ".."
```

## Using multistage builder cache

Docker multistage build cache can speed up your builds. Currently, Kamal only supports using the GHA cache or the Registry cache:

```yaml
# Using GHA cache
builder:
  cache:
    type: gha

# Using Registry cache
builder:
  cache:
    type: registry

# Using Registry cache with different cache image
builder:
  cache:
    type: registry
    # default image name is <image>-build-cache
    image: application-cache-image

# Using Registry cache with additional cache-to options
builder:
  cache:
    type: registry
    options: mode=max,image-manifest=true,oci-mediatypes=true
```

## Building without a Dockerfile locally

Your application image can also be built using cloud native buildpacks instead of using a `Dockerfile` and the default `docker build` process. This example uses Heroku's ruby and Procfile buildpacks to build your final image.

```yaml
  pack:
    builder: heroku/builder:24
    buildpacks:
      - heroku/ruby
      - heroku/procfile
```

To provide any additional customizations you can add a project descriptor file (`project.toml`) in the root of your application.

### GHA cache configuration

To make it work on the GitHub action workflow, you need to set up the buildx and expose authentication configuration for the cache.

Example setup (in .github/workflows/sample-ci.yml):

```yaml
- name: Set up Docker Buildx for cache
  uses: docker/setup-buildx-action@v3

- name: Expose GitHub Runtime for cache
  uses: crazy-max/ghaction-github-runtime@v3
```

When set up correctly, you should see the cache entry/entries on the GHA workflow actions cache section.

For further insights into build cache optimization, check out the documentation on Docker's official website: https://docs.docker.com/build/cache/.

## Using build secrets for new images

Some images need a secret passed in during build time, like a GITHUB\_TOKEN, to give access to private gem repositories. This can be done by setting the secret in `.kamal/secrets`, then referencing it in the builder configuration:

```bash
# .kamal/secrets

GITHUB_TOKEN=$(gh config get -h github.com oauth_token)
```

```yaml
# config/deploy.yml

builder:
  secrets:
    - GITHUB_TOKEN
```

This build secret can then be referenced in the Dockerfile:

```dockerfile
# Copy Gemfiles
COPY Gemfile Gemfile.lock ./

# Install dependencies, including private repositories via access token (then remove bundle cache with exposed GITHUB_TOKEN)
RUN --mount=type=secret,id=GITHUB_TOKEN \
  BUNDLE_GITHUB__COM=x-access-token:$(cat /run/secrets/GITHUB_TOKEN) \
  bundle install && \
  rm -rf /usr/local/bundle/cache
```

## Configuring build args for new images

Build arguments that aren't secret can also be configured:

```yaml
builder:
  args:
    RUBY_VERSION: 3.2.0
```

This build argument can then be used in the Dockerfile:

```dockerfile
ARG RUBY_VERSION
FROM ruby:$RUBY_VERSION-slim as base
```

# overview.md

# Kamal Configuration

Configuration is read from the `config/deploy.yml`.

## Destinations

When running commands, you can specify a destination with the `-d` flag,
e.g., `kamal deploy -d staging`.

In this case, the configuration will also be read from `config/deploy.staging.yml`
and merged with the base configuration.

## Extensions

Kamal will not accept unrecognized keys in the configuration file.

However, you might want to declare a configuration block using YAML anchors
and aliases to avoid repetition.

You can prefix a configuration section with `x-` to indicate that it is an
extension. Kamal will ignore the extension and not raise an error.

## The service name

This is a required value. It is used as the container name prefix.

```yaml
service: myapp
```

## The Docker image name

The image will be pushed to the configured registry.

```yaml
image: my-image
```

## Labels

Additional labels to add to the container:

```yaml
labels:
  my-label: my-value
```

## Volumes

Additional volumes to mount into the container:

```yaml
volumes:
  - /path/on/host:/path/in/container:ro
```

## Registry

The Docker registry configuration, see Docker Registry:

```yaml
registry:
  ...
```

## Servers

The servers to deploy to, optionally with custom roles, see Servers:

```yaml
servers:
  ...
```

## Environment variables

See Environment variables:

```yaml
env:
  ...
```

## Asset path

Used for asset bridging across deployments, default to `nil`.

If there are changes to CSS or JS files, we may get requests
for the old versions on the new container, and vice versa.

To avoid 404s, we can specify an asset path.
Kamal will replace that path in the container with a mapped
volume containing both sets of files.
This requires that file names change when the contents change
(e.g., by including a hash of the contents in the name).

To configure this, set the path to the assets:

```yaml
asset_path: /path/to/assets
```

## Hooks path

Path to hooks, defaults to `.kamal/hooks`.
See Hooks for more information:

```yaml
hooks_path: /user_home/kamal/hooks
```

## Error pages

A directory relative to the app root to find error pages for the proxy to serve.
Any files in the format 4xx.html or 5xx.html will be copied to the hosts.

```yaml
error_pages_path: public
```

## Require destinations

Whether deployments require a destination to be specified, defaults to `false`:

```yaml
require_destination: true
```

## Primary role

This defaults to `web`, but if you have no web role, you can change this:

```yaml
primary_role: workers
```

## Allowing empty roles

Whether roles with no servers are allowed. Defaults to `false`:

```yaml
allow_empty_roles: false
```

## Retain containers

How many old containers and images we retain, defaults to 5:

```yaml
retain_containers: 3
```

## Minimum version

The minimum version of Kamal required to deploy this configuration, defaults to `nil`:

```yaml
minimum_version: 1.3.0
```

## Readiness delay

Seconds to wait for a container to boot after it is running, default 7.

This only applies to containers that do not run a proxy or specify a healthcheck:

```yaml
readiness_delay: 4
```

## Deploy timeout

How long to wait for a container to become ready, default 30:

```yaml
deploy_timeout: 10
```

## Drain timeout

How long to wait for a container to drain, default 30:

```yaml
drain_timeout: 10
```

## Run directory

Directory to store kamal runtime files in on the host, default `.kamal`:

```yaml
run_directory: /etc/kamal
```

## SSH options

See SSH:

```yaml
ssh:
  ...
```

## Builder options

See Builders:

```yaml
builder:
  ...
```

## Accessories

Additional services to run in Docker, see Accessories:

```yaml
accessories:
  ...
```

## Proxy

Configuration for kamal-proxy, see Proxy:

```yaml
proxy:
  ...
```

## SSHKit

See SSHKit:

```yaml
sshkit:
  ...
```

## Boot options

See Booting:

```yaml
boot:
  ...
```

## Logging

Docker logging configuration, see Logging:

```yaml
logging:
  ...
```

## Aliases

Alias configuration, see Aliases:

```yaml
aliases:
  ...
```

# environment-variables.md

# Environment variables

Environment variables can be set directly in the Kamal configuration or
read from `.kamal/secrets`.

## Reading environment variables from the configuration

Environment variables can be set directly in the configuration file.

These are passed to the `docker run` command when deploying.

```yaml
env:
  DATABASE_HOST: mysql-db1
  DATABASE_PORT: 3306
```

## Secrets

Kamal uses dotenv to automatically load environment variables set in the `.kamal/secrets` file.

If you are using destinations, secrets will instead be read from `.kamal/secrets.<DESTINATION>` if
it exists.

Common secrets across all destinations can be set in `.kamal/secrets-common`.

This file can be used to set variables like `KAMAL_REGISTRY_PASSWORD` or database passwords.
You can use variable or command substitution in the secrets file.

```shell
KAMAL_REGISTRY_PASSWORD=$KAMAL_REGISTRY_PASSWORD
RAILS_MASTER_KEY=$(cat config/master.key)
```

You can also use secret helpers for some common password managers.

```shell
SECRETS=$(kamal secrets fetch ...)

REGISTRY_PASSWORD=$(kamal secrets extract REGISTRY_PASSWORD $SECRETS)
DB_PASSWORD=$(kamal secrets extract DB_PASSWORD $SECRETS)
```

If you store secrets directly in `.kamal/secrets`, ensure that it is not checked into version control.

To pass the secrets, you should list them under the `secret` key. When you do this, the
other variables need to be moved under the `clear` key.

Unlike clear values, secrets are not passed directly to the container
but are stored in an env file on the host:

```yaml
env:
  clear:
    DB_USER: app
  secret:
    - DB_PASSWORD
```

## Aliased secrets

You can also alias secrets to other secrets using a `:` separator.

This is useful when the ENV name is different from the secret name. For example, if you have two
places where you need to define the ENV variable `DB_PASSWORD`, but the value is different depending
on the context.

```shell
SECRETS=$(kamal secrets fetch ...)

MAIN_DB_PASSWORD=$(kamal secrets extract MAIN_DB_PASSWORD $SECRETS)
SECONDARY_DB_PASSWORD=$(kamal secrets extract SECONDARY_DB_PASSWORD $SECRETS)
```

```yaml
env:
  secret:
    - DB_PASSWORD:MAIN_DB_PASSWORD
  tags:
    secondary_db:
      secret:
        - DB_PASSWORD:SECONDARY_DB_PASSWORD
accessories:
  main_db_accessory:
    env:
      secret:
        - DB_PASSWORD:MAIN_DB_PASSWORD
  secondary_db_accessory:
    env:
      secret:
        - DB_PASSWORD:SECONDARY_DB_PASSWORD
```

## Tags

Tags are used to add extra env variables to specific hosts.
See Servers for how to tag hosts.

Tags are only allowed in the top-level env configuration (i.e., not under a role-specific env).

The env variables can be specified with secret and clear values as explained above.

```yaml
env:
  tags:
    <tag1>:
      MYSQL_USER: monitoring
    <tag2>:
      clear:
        MYSQL_USER: readonly
      secret:
        - MYSQL_PASSWORD
```

## Example configuration

```yaml
env:
  clear:
    MYSQL_USER: app
  secret:
    - MYSQL_PASSWORD
  tags:
    monitoring:
      MYSQL_USER: monitoring
    replica:
      clear:
        MYSQL_USER: readonly
      secret:
        - READONLY_PASSWORD
```

# aliases.md

# Aliases

Aliases are shortcuts for Kamal commands.

For example, for a Rails app, you might open a console with:

```shell
kamal app exec -i --reuse "bin/rails console"
```

By defining an alias, like this:

```yaml
aliases:
  console: app exec -i --reuse "bin/rails console"
```

You can now open the console with:

```shell
kamal console
```

## Configuring aliases

Aliases are defined in the root config under the alias key.

Each alias is named and can only contain lowercase letters, numbers, dashes, and underscores:

```yaml
aliases:
  uname: app exec -p -q -r web "uname -a"
```

# anchors.md

# Anchors

You can re-use parts of your Kamal configuration by defining them as anchors and referencing them with aliases.

For example, you might need to define a shared healthcheck for multiple worker roles. Anchors
begin with `x-` and are defined at the root level of your deploy.yml file.

```yaml
x-worker-healthcheck: &worker-healthcheck
  health-cmd: bin/worker-healthcheck
  health-start-period: 5s
  health-retries: 5
  health-interval: 5s
```

To use this anchor in your deploy configuration, reference it via the alias.

```yaml
servers:
  worker:
    hosts:
      - 867.53.0.9
    cmd: bin/jobs
    options:
      <<: *worker-healthcheck
```

# accessories.md

# Accessories

Accessories can be booted on a single host, a list of hosts, or on specific roles.
The hosts do not need to be defined in the Kamal servers configuration.

Accessories are managed separately from the main service — they are not updated
when you deploy, and they do not have zero-downtime deployments.

Run `kamal accessory boot <accessory>` to boot an accessory.
See `kamal accessory --help` for more information.

## Configuring accessories

First, define the accessory in the `accessories`:

```yaml
accessories:
  mysql:
```

## Service name

This is used in the service label and defaults to `<service>-<accessory>`,
where `<service>` is the main service name from the root configuration:

```yaml
    service: mysql
```

## Image

The Docker image to use.
Prefix it with its server when using root level registry different from Docker Hub.
Define registry directly or via anchors when it differs from root level registry.

```yaml
    image: mysql:8.0
```

## Registry

By default accessories use Docker Hub registry.
You can specify different registry per accessory with this option.
Don't prefix image with this registry server.
Use anchors if you need to set the same specific registry for several accessories.

```yml
registry:
  <<: *specific-registry
```

See Docker Registry for more information:

```yaml
    registry:
      ...
```

## Accessory hosts

Specify one of `host`, `hosts`, `role`, `roles`, `tag` or `tags`:

```yaml
    host: mysql-db1
    hosts:
      - mysql-db1
      - mysql-db2
    role: mysql
    roles:
      - mysql
    tag: writer
    tags:
      - writer
      - reader
```

## Custom command

You can set a custom command to run in the container if you do not want to use the default:

```yaml
    cmd: "bin/mysqld"
```

## Port mappings

See https://docs.docker.com/network/, and
especially note the warning about the security implications of exposing ports publicly.

```yaml
    port: "127.0.0.1:3306:3306"
```

## Labels

```yaml
    labels:
      app: myapp
```

## Options

These are passed to the Docker run command in the form `--<name> <value>`:

```yaml
    options:
      restart: always
      cpus: 2
```

## Environment variables

See Environment variables for more information:

```yaml
    env:
      ...
```

## Copying files

You can specify files to mount into the container.
The format is `local:remote`, where `local` is the path to the file on the local machine
and `remote` is the path to the file in the container.

They will be uploaded from the local repo to the host and then mounted.

ERB files will be evaluated before being copied.

```yaml
    files:
      - config/my.cnf.erb:/etc/mysql/my.cnf
      - config/myoptions.cnf:/etc/mysql/myoptions.cnf
```

## Directories

You can specify directories to mount into the container. They will be created on the host
before being mounted:

```yaml
    directories:
      - mysql-logs:/var/log/mysql
```

## Volumes

Any other volumes to mount, in addition to the files and directories.
They are not created or copied before mounting:

```yaml
    volumes:
      - /path/to/mysql-logs:/var/log/mysql
```

## Network

The network the accessory will be attached to.

Defaults to kamal:

```yaml
    network: custom
```

## Proxy

You can run your accessory behind the Kamal proxy. See Proxy for more information

```yaml
    proxy:
      ...
```

# ssh.md

# SSH configuration

Kamal uses SSH to connect and run commands on your hosts.
By default, it will attempt to connect to the root user on port 22.

If you are using a non-root user, you may need to bootstrap your servers manually before using them with Kamal. On Ubuntu, you’d do:

```shell
sudo apt update
sudo apt upgrade -y
sudo apt install -y docker.io curl git
sudo usermod -a -G docker app
```

## SSH options

The options are specified under the ssh key in the configuration file.

```yaml
ssh:
```

## The SSH user

Defaults to `root`:

```yaml
  user: app
```

## The SSH port

Defaults to 22:

```yaml
  port: "2222"
```

## Proxy host

Specified in the form <host> or <user>@<host>:

```yaml
  proxy: root@proxy-host
```

## Proxy command

A custom proxy command, required for older versions of SSH:

```yaml
  proxy_command: "ssh -W %h:%p user@proxy"
```

## Log level

Defaults to `fatal`. Set this to `debug` if you are having SSH connection issues.

```yaml
  log_level: debug
```

## Keys only

Set to `true` to use only private keys from the `keys` and `key_data` parameters,
even if ssh-agent offers more identities. This option is intended for
situations where ssh-agent offers many different identities or you
need to overwrite all identities and force a single one.

```yaml
  keys_only: false
```

## Keys

An array of file names of private keys to use for public key
and host-based authentication:

```yaml
  keys: [ "~/.ssh/id.pem" ]
```

## Key data

An array of strings, with each element of the array being
a raw private key in PEM format.

```yaml
  key_data: [ "-----BEGIN OPENSSH PRIVATE KEY-----" ]
```

## Config

Set to true to load the default OpenSSH config files (~/.ssh/config,
/etc/ssh\_config), to false ignore config files, or to a file path
(or array of paths) to load specific configuration. Defaults to true.

```yaml
  config: true
```

# sshkit.md

# SSHKit

SSHKit is the SSH toolkit used by Kamal.

The default, settings should be sufficient for most use cases, but
when connecting to a large number of hosts, you may need to adjust.

## SSHKit options

The options are specified under the sshkit key in the configuration file.

```yaml
sshkit:
```

## Max concurrent starts

Creating SSH connections concurrently can be an issue when deploying to many servers.
By default, Kamal will limit concurrent connection starts to 30 at a time.

```yaml
  max_concurrent_starts: 10
```

## Pool idle timeout

Kamal sets a long idle timeout of 900 seconds on connections to try to avoid
re-connection storms after an idle period, such as building an image or waiting for CI.

```yaml
  pool_idle_timeout: 300
```

# roles.md

# Roles

Roles are used to configure different types of servers in the deployment.
The most common use for this is to run web servers and job servers.

Kamal expects there to be a `web` role, unless you set a different `primary_role`
in the root configuration.

## Role configuration

Roles are specified under the servers key:

```yaml
servers:
```

## Simple role configuration

This can be a list of hosts if you don't need custom configuration for the role.

You can set tags on the hosts for custom env variables (see Environment variables):

```yaml
  web:
    - 172.1.0.1
    - 172.1.0.2: experiment1
    - 172.1.0.2: [ experiment1, experiment2 ]
```

## Custom role configuration

When there are other options to set, the list of hosts goes under the `hosts` key.

By default, only the primary role uses a proxy.

For other roles, you can set it to `proxy: true` to enable it and inherit the root proxy
configuration or provide a map of options to override the root configuration.

For the primary role, you can set `proxy: false` to disable the proxy.

You can also set a custom `cmd` to run in the container and overwrite other settings
from the root configuration.

```yaml
  workers:
    hosts:
      - 172.1.0.3
      - 172.1.0.4: experiment1
    cmd: "bin/jobs"
    options:
      memory: 2g
      cpus: 4
    logging:
      ...
    proxy:
      ...
    labels:
      my-label: workers
    env:
      ...
    asset_path: /public
```

# index.md

# logging.md

# Custom logging configuration

Set these to control the Docker logging driver and options.

## Logging settings

These go under the logging key in the configuration file.

This can be specified at the root level or for a specific role.

```yaml
logging:
```

## Driver

The logging driver to use, passed to Docker via `--log-driver`:

```yaml
  driver: json-file
```

## Options

Any logging options to pass to the driver, passed to Docker via `--log-opt`:

```yaml
  options:
    max-size: 100m
```

# builders.md

# Builder

The builder configuration controls how the application is built with `docker build`.

See Builder examples for more information.

## Builder options

Options go under the builder key in the root configuration.

```yaml
builder:
```

## Arch

The architectures to build for — you can set an array or just a single value.

Allowed values are `amd64` and `arm64`:

```yaml
  arch:
    - amd64
```

## Remote

The connection string for a remote builder. If supplied, Kamal will use this
for builds that do not match the local architecture of the deployment host.

```yaml
  remote: ssh://docker@docker-builder
```

## Local

If set to false, Kamal will always use the remote builder even when building
the local architecture.

Defaults to true:

```yaml
  local: true
```

## Buildpack configuration

The build configuration for using pack to build a Cloud Native Buildpack image.

For additional buildpack customization options you can create a project descriptor
file(project.toml) that the Pack CLI will automatically use.
See https://buildpacks.io/docs/for-app-developers/how-to/build-inputs/use-project-toml/ for more information.

```yaml
  pack:
    builder: heroku/builder:24
    buildpacks:
      - heroku/ruby
      - heroku/procfile
```

## Builder cache

The type must be either 'gha' or 'registry'.

The image is only used for registry cache and is not compatible with the Docker driver:

```yaml
  cache:
    type: registry
    options: mode=max
    image: kamal-app-build-cache
```

## Build context

If this is not set, then a local Git clone of the repo is used.
This ensures a clean build with no uncommitted changes.

To use the local checkout instead, you can set the context to `.`, or a path to another directory.

```yaml
  context: .
```

## Dockerfile

The Dockerfile to use for building, defaults to `Dockerfile`:

```yaml
  dockerfile: Dockerfile.production
```

## Build target

If not set, then the default target is used:

```yaml
  target: production
```

## Build arguments

Any additional build arguments, passed to `docker build` with `--build-arg <key>=<value>`:

```yaml
  args:
    ENVIRONMENT: production
```

## Referencing build arguments

```shell
ARG RUBY_VERSION
FROM ruby:$RUBY_VERSION-slim as base
```

## Build secrets

Values are read from `.kamal/secrets`:

```yaml
  secrets:
    - SECRET1
    - SECRET2
```

## Referencing build secrets

```shell
# Copy Gemfiles
COPY Gemfile Gemfile.lock ./

# Install dependencies, including private repositories via access token
# Then remove bundle cache with exposed GITHUB_TOKEN
RUN --mount=type=secret,id=GITHUB_TOKEN \
  BUNDLE_GITHUB__COM=x-access-token:$(cat /run/secrets/GITHUB_TOKEN) \
  bundle install && \
  rm -rf /usr/local/bundle/cache
```

## SSH

SSH agent socket or keys to expose to the build:

```yaml
  ssh: default=$SSH_AUTH_SOCK
```

## Driver

The build driver to use, defaults to `docker-container`:

```yaml
  driver: docker
```

If you want to use Docker Build Cloud (https://www.docker.com/products/build-cloud/), you can set the driver to:

```yaml
  driver: cloud org-name/builder-name
```

## Provenance

It is used to configure provenance attestations for the build result.
The value can also be a boolean to enable or disable provenance attestations.

```yaml
  provenance: mode=max
```

## SBOM (Software Bill of Materials)

It is used to configure SBOM generation for the build result.
The value can also be a boolean to enable or disable SBOM generation.

```yaml
  sbom: true
```

# docker-registry.md

# Registry

The default registry is Docker Hub, but you can change it using `registry/server`.

By default, Docker Hub creates public repositories. To avoid making your images public,
set up a private repository before deploying, or change the default repository privacy
settings to private in your Docker Hub settings.

A reference to a secret (in this case, `DOCKER_REGISTRY_TOKEN`) will look up the secret
in the local environment:

```yaml
registry:
  server: registry.digitalocean.com
  username:
    - DOCKER_REGISTRY_TOKEN
  password:
    - DOCKER_REGISTRY_TOKEN
```

## Using AWS ECR as the container registry

You will need to have the AWS CLI installed locally for this to work.
AWS ECR’s access token is only valid for 12 hours. In order to avoid having to manually regenerate the token every time, you can use ERB in the `deploy.yml` file to shell out to the AWS CLI command and obtain the token:

```yaml
registry:
  server: <your aws account id>.dkr.ecr.<your aws region id>.amazonaws.com
  username: AWS
  password: <%= %x(aws ecr get-login-password) %>
```

## Using GCP Artifact Registry as the container registry

To sign into Artifact Registry, you need to
create a service account
and set up roles and permissions.
Normally, assigning the `roles/artifactregistry.writer` role should be sufficient.

Once the service account is ready, you need to generate and download a JSON key and base64 encode it:

```shell
base64 -i /path/to/key.json | tr -d "\\n"
```

You'll then need to set the `KAMAL_REGISTRY_PASSWORD` secret to that value.

Use the environment variable as the password along with `_json_key_base64` as the username.
Here’s the final configuration:

```yaml
registry:
  server: <your registry region>-docker.pkg.dev
  username: _json_key_base64
  password:
    - KAMAL_REGISTRY_PASSWORD
```

## Validating the configuration

You can validate the configuration by running:

```shell
kamal registry login
```

# booting.md

# Booting

When deploying to large numbers of hosts, you might prefer not to restart your services on every host at the same time.

Kamal’s default is to boot new containers on all hosts in parallel. However, you can control this with the boot configuration.

## Fixed group sizes

Here, we boot 2 hosts at a time with a 10-second gap between each group:

```yaml
boot:
  limit: 2
  wait: 10
```

## Percentage of hosts

Here, we boot 25% of the hosts at a time with a 2-second gap between each group:

```yaml
boot:
  limit: 25%
  wait: 2
```

# servers.md

# Servers

Servers are split into different roles, with each role having its own configuration.

For simpler deployments, though, where all servers are identical, you can just specify a list of servers.
They will be implicitly assigned to the `web` role.

```yaml
servers:
  - 172.0.0.1
  - 172.0.0.2
  - 172.0.0.3
```

## Tagging servers

Servers can be tagged, with the tags used to add custom env variables (see Environment variables).

```yaml
servers:
  - 172.0.0.1
  - 172.0.0.2: experiments
  - 172.0.0.3: [ experiments, three ]
```

## Roles

For more complex deployments (e.g., if you are running job hosts), you can specify roles and configure each separately (see Roles):

```yaml
servers:
  web:
    ...
  workers:
    ...
```

# cron.md

# Cron

You can use a specific container to run your Cron jobs:

```yaml
servers:
  cron:
    hosts:
      - 192.168.0.1
    cmd:
      bash -c "(env && cat config/crontab) | crontab - && cron -f"
```

This assumes that the Cron settings are stored in `config/crontab`. Cron does not automatically propagate environment variables, the example above copies them into the crontab.

# proxy.md

# Proxy

Kamal uses kamal-proxy to provide
gapless deployments. It runs on ports 80 and 443 and forwards requests to the
application container.

The proxy is configured in the root configuration under `proxy`. These are
options that are set when deploying the application, not when booting the proxy.

They are application-specific, so they are not shared when multiple applications
run on the same proxy.

```yaml
proxy:
```

## Hosts

The hosts that will be used to serve the app. The proxy will only route requests
to this host to your app.

If no hosts are set, then all requests will be forwarded, except for matching
requests for other apps deployed on that server that do have a host set.

Specify one of `host` or `hosts`.

```yaml
  host: foo.example.com
  hosts:
    - foo.example.com
    - bar.example.com
```

## App port

The port the application container is exposed on.

Defaults to 80:

```yaml
  app_port: 3000
```

## SSL

kamal-proxy can provide automatic HTTPS for your application via Let's Encrypt.

This requires that we are deploying to one server and the host option is set.
The host value must point to the server we are deploying to, and port 443 must be
open for the Let's Encrypt challenge to succeed.

If you set `ssl` to `true`, `kamal-proxy` will stop forwarding headers to your app,
unless you explicitly set `forward_headers: true`

Defaults to `false`:

```yaml
  ssl: true
```

## Custom SSL certificate

In some cases, using Let's Encrypt for automatic certificate management is not an
option, for example if you are running from more than one host.

Or you may already have SSL certificates issued by a different Certificate Authority (CA).

Kamal supports loading custom SSL certificates directly from secrets. You should
pass a hash mapping the `certificate_pem` and `private_key_pem` to the secret names.

```yaml
  ssl:
    certificate_pem: CERTIFICATE_PEM
    private_key_pem: PRIVATE_KEY_PEM
```

### Notes

* If the certificate or key is missing or invalid, deployments will fail.
* Always handle SSL certificates and private keys securely. Avoid hard-coding them in source control.

## SSL redirect

By default, kamal-proxy will redirect all HTTP requests to HTTPS when SSL is enabled.
If you prefer that HTTP traffic is passed through to your application (along with
HTTPS traffic), you can disable this redirect by setting `ssl_redirect: false`:

```yaml
  ssl_redirect: false
```

## Forward headers

Whether to forward the `X-Forwarded-For` and `X-Forwarded-Proto` headers.

If you are behind a trusted proxy, you can set this to `true` to forward the headers.

By default, kamal-proxy will not forward the headers if the `ssl` option is set to `true`, and
will forward them if it is set to `false`.

```yaml
  forward_headers: true
```

## Response timeout

How long to wait for requests to complete before timing out, defaults to 30 seconds:

```yaml
  response_timeout: 10
```

## Path-based routing

For applications that split their traffic to different services based on the request path,
you can use path-based routing to mount services under different path prefixes.

```yaml
  path_prefix: '/api'
```

By default, the path prefix will be stripped from the request before it is forwarded upstream.
So in the example above, a request to /api/users/123 will be forwarded to web-1 as /users/123.
To instead forward the request with the original path (including the prefix),
specify --strip-path-prefix=false

```yaml
  strip_path_prefix: false
```

## Healthcheck

When deploying, the proxy will by default hit `/up` once every second until we hit
the deploy timeout, with a 5-second timeout for each request.

Once the app is up, the proxy will stop hitting the healthcheck endpoint.

```yaml
  healthcheck:
    interval: 3
    path: /health
    timeout: 3
```

## Buffering

Whether to buffer request and response bodies in the proxy.

By default, buffering is enabled with a max request body size of 1GB and no limit
for response size.

You can also set the memory limit for buffering, which defaults to 1MB; anything
larger than that is written to disk.

```yaml
  buffering:
    requests: true
    responses: true
    max_request_body: 40_000_000
    max_response_body: 0
    memory: 2_000_000
```

## Logging

Configure request logging for the proxy.
You can specify request and response headers to log.
By default, `Cache-Control`, `Last-Modified`, and `User-Agent` request headers are logged:

```yaml
  logging:
    request_headers:
      - Cache-Control
      - X-Forwarded-Proto
    response_headers:
      - X-Request-ID
      - X-Request-Start
```

## Enabling/disabling the proxy on roles

The proxy is enabled by default on the primary role but can be disabled by
setting `proxy: false` in the primary role's configuration.

```yaml
servers:
  web:
    hosts:
     - ...
    proxy: false
```

It is disabled by default on all other roles but can be enabled by setting
`proxy: true` or providing a proxy configuration for that role.

```yaml
servers:
  web:
    hosts:
     - ...
  web2:
    hosts:
     - ...
    proxy: true
```

# lock.md

# kamal lock

Manage deployment locks.

Commands that are unsafe to run concurrently will take a lock while they run. The lock is an atomically created directory in the `.kamal` directory on the primary server.

You can manage them directly — for example, clearing a leftover lock from a failed command or preventing deployments during a maintenance window.

```bash
$ kamal lock
Commands:
  kamal lock acquire -m, --message=MESSAGE  # Acquire the deploy lock
  kamal lock help [COMMAND]                 # Describe subcommands or one specific subcommand
  kamal lock release                        # Release the deploy lock
  kamal lock status                         # Report lock status
```

Example:

```bash
$ kamal lock status
  INFO [f085f083] Running /usr/bin/env mkdir -p .kamal on server1
  INFO [f085f083] Finished in 0.146 seconds with exit status 0 (successful).
There is no deploy lock
$ kamal lock acquire -m "Maintenance in progress"
  INFO [d9f63437] Running /usr/bin/env mkdir -p .kamal on server1
  INFO [d9f63437] Finished in 0.138 seconds with exit status 0 (successful).
Acquired the deploy lock
$ kamal lock status
  INFO [9315755d] Running /usr/bin/env mkdir -p .kamal on server1
  INFO [9315755d] Finished in 0.130 seconds with exit status 0 (successful).
Locked by: Deployer at 2024-04-05T08:32:46Z
Version: 75bf6fa40b975cbd8aec05abf7164e0982f185ac
Message: Maintenance in progress
$ kamal lock release
  INFO [7d5718a8] Running /usr/bin/env mkdir -p .kamal on server1
  INFO [7d5718a8] Finished in 0.137 seconds with exit status 0 (successful).
Released the deploy lock
$ kamal lock status
  INFO [f5900cc8] Running /usr/bin/env mkdir -p .kamal on server1
  INFO [f5900cc8] Finished in 0.132 seconds with exit status 0 (successful).
There is no deploy lock
```

# running-commands-on-servers.md

# Running commands on servers

You can use aliases for common commands.

## Run command on all servers

```bash
$ kamal app exec 'ruby -v'
App Host: 192.168.0.1
ruby 3.1.3p185 (2022-11-24 revision 1a6b16756e) [x86_64-linux]

App Host: 192.168.0.2
ruby 3.1.3p185 (2022-11-24 revision 1a6b16756e) [x86_64-linux]
```

## Run command on primary server

```bash
$ kamal app exec --primary 'cat .ruby-version'
App Host: 192.168.0.1
3.1.3
```

## Run Rails command on all servers

```bash
$ kamal app exec 'bin/rails about'
App Host: 192.168.0.1
About your application's environment
Rails version             7.1.0.alpha
Ruby version              ruby 3.1.3p185 (2022-11-24 revision 1a6b16756e) [x86_64-linux]
RubyGems version          3.3.26
Rack version              2.2.5
Middleware                ActionDispatch::HostAuthorization, Rack::Sendfile, ActionDispatch::Static, ActionDispatch::Executor, Rack::Runtime, Rack::MethodOverride, ActionDispatch::RequestId, ActionDispatch::RemoteIp, Rails::Rack::Logger, ActionDispatch::ShowExceptions, ActionDispatch::DebugExceptions, ActionDispatch::Callbacks, ActionDispatch::Cookies, ActionDispatch::Session::CookieStore, ActionDispatch::Flash, ActionDispatch::ContentSecurityPolicy::Middleware, ActionDispatch::PermissionsPolicy::Middleware, Rack::Head, Rack::ConditionalGet, Rack::ETag, Rack::TempfileReaper
Application root          /rails
Environment               production
Database adapter          sqlite3
Database schema version   20221231233303

App Host: 192.168.0.2
About your application's environment
Rails version             7.1.0.alpha
Ruby version              ruby 3.1.3p185 (2022-11-24 revision 1a6b16756e) [x86_64-linux]
RubyGems version          3.3.26
Rack version              2.2.5
Middleware                ActionDispatch::HostAuthorization, Rack::Sendfile, ActionDispatch::Static, ActionDispatch::Executor, Rack::Runtime, Rack::MethodOverride, ActionDispatch::RequestId, ActionDispatch::RemoteIp, Rails::Rack::Logger, ActionDispatch::ShowExceptions, ActionDispatch::DebugExceptions, ActionDispatch::Callbacks, ActionDispatch::Cookies, ActionDispatch::Session::CookieStore, ActionDispatch::Flash, ActionDispatch::ContentSecurityPolicy::Middleware, ActionDispatch::PermissionsPolicy::Middleware, Rack::Head, Rack::ConditionalGet, Rack::ETag, Rack::TempfileReaper
Application root          /rails
Environment               production
Database adapter          sqlite3
Database schema version   20221231233303
```

## Run Rails runner on primary server

```bash
$ kamal app exec -p 'bin/rails runner "puts Rails.application.config.time_zone"'
UTC
```

## Run interactive commands over SSH

You can run interactive commands, like a Rails console or a bash session, on a server (default is primary, use `--hosts` to connect to another).

Start a bash session in a new container made from the most recent app image:

```bash
kamal app exec -i bash
```

Start a bash session in the currently running container for the app:

```bash
kamal app exec -i --reuse bash
```

Start a Rails console in a new container made from the most recent app image:

```bash
kamal app exec -i 'bin/rails console'
```

# redeploy.md

# kamal redeploy

Deploy your app, but skip bootstrapping servers, starting kamal-proxy, pruning, and registry login.

You must run `kamal deploy` at least once first.

# prune.md

# kamal prune

Prune old containers and images.

Kamal keeps the last 5 deployed containers and the images they are using. Pruning deletes all older containers and images.

```bash
$ kamal prune
Commands:
  kamal prune all             # Prune unused images and stopped containers
  kamal prune containers      # Prune all stopped containers, except the last n (default 5)
  kamal prune help [COMMAND]  # Describe subcommands or one specific subcommand
  kamal prune images          # Prune unused images
```

# app.md

# kamal app

Run `kamal app` to manage your running apps.

To deploy new versions of the app, see `kamal deploy` and `kamal rollback`.

You can use `kamal app exec` to run commands on servers.

```bash
$ kamal app
Commands:
  kamal app boot              # Boot app on servers (or reboot app if already running)
  kamal app containers        # Show app containers on servers
  kamal app details           # Show details about app containers
  kamal app exec [CMD...]     # Execute a custom command on servers within the app container (use --help to show options)
  kamal app help [COMMAND]    # Describe subcommands or one specific subcommand
  kamal app images            # Show app images on servers
  kamal app live              # Set the app to live mode
  kamal app logs              # Show log lines from app on servers (use --help to show options)
  kamal app maintenance       # Set the app to maintenance mode
  kamal app remove            # Remove app containers and images from servers
  kamal app stale_containers  # Detect app stale containers
  kamal app start             # Start existing app container on servers
  kamal app stop              # Stop app container on servers
  kamal app version           # Show app version currently running on servers
```

## Maintenance Mode

You can set your application to maintenance mode, by running `kamal app maintenance`.

When in maintenance mode, kamal-proxy will intercept requests and return a 503 responses.

There is a built in HTML template for the error page. You can customise the error message
via the --message option:

```shell
$ kamal app maintenance --message "Scheduled maintenance window from ..."
```

You can also provide custom error pages by setting the `error_pages_path` configuration option.

## Live Mode

You can set your application back to live mode, by running `kamal app live`.

# secrets.md

# kamal secrets

```bash
$ kamal secrets
Commands:
  kamal secrets extract                                                     # Extract a single secret from the results of a fetch call
  kamal secrets fetch [SECRETS...] --account=ACCOUNT -a, --adapter=ADAPTER  # Fetch secrets from a vault
  kamal secrets help [COMMAND]                                              # Describe subcommands or one specific subcommand
  kamal secrets print                                                       # Print the secrets (for debugging)
```

Use these to read secrets from common password managers (currently 1Password, LastPass, and Bitwarden).

The helpers will handle signing in, asking for passwords, and efficiently fetching the secrets:

These are designed to be used with command substitution in `.kamal/secrets`

```shell
# .kamal/secrets

SECRETS=$(kamal secrets fetch ...)

REGISTRY_PASSWORD=$(kamal secrets extract REGISTRY_PASSWORD $SECRETS)
DB_PASSWORD=$(kamal secrets extract DB_PASSWORD $SECRETS)
```

## 1Password

First, install and configure the 1Password CLI.

Use the adapter `1password`:

```bash
# Fetch from item `MyItem` in the vault `MyVault`
kamal secrets fetch --adapter 1password --account myaccount --from MyVault/MyItem REGISTRY_PASSWORD DB_PASSWORD

# Fetch from sections of item `MyItem` in the vault `MyVault`
kamal secrets fetch --adapter 1password --account myaccount --from MyVault/MyItem common/REGISTRY_PASSWORD production/DB_PASSWORD

# Fetch from separate items MyItem, MyItem2
kamal secrets fetch --adapter 1password --account myaccount --from MyVault MyItem/REGISTRY_PASSWORD MyItem2/DB_PASSWORD

# Fetch from multiple vaults
kamal secrets fetch --adapter 1password --account myaccount MyVault/MyItem/REGISTRY_PASSWORD MyVault2/MyItem2/DB_PASSWORD

# All three of these will extract the secret
kamal secrets extract REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
kamal secrets extract MyItem/REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
kamal secrets extract MyVault/MyItem/REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
```

## LastPass

First, install and configure the LastPass CLI.

Use the adapter `lastpass`:

```bash
# Fetch passwords
kamal secrets fetch --adapter lastpass --account email@example.com REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from a folder
kamal secrets fetch --adapter lastpass --account email@example.com --from MyFolder REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from multiple folders
kamal secrets fetch --adapter lastpass --account email@example.com MyFolder/REGISTRY_PASSWORD MyFolder2/DB_PASSWORD

# Extract the secret
kamal secrets extract REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
kamal secrets extract MyFolder/REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
```

## Bitwarden

First, install and configure the Bitwarden CLI.

Use the adapter `bitwarden`:

```bash
# Fetch passwords
kamal secrets fetch --adapter bitwarden --account email@example.com REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from an item
kamal secrets fetch --adapter bitwarden --account email@example.com --from MyItem REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from multiple items
kamal secrets fetch --adapter bitwarden --account email@example.com MyItem/REGISTRY_PASSWORD MyItem2/DB_PASSWORD

# Extract the secret
kamal secrets extract REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
kamal secrets extract MyItem/REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
```

## Bitwarden Secrets Manager

First, install and configure the Bitwarden Secrets Manager CLI.

Use the adapter 'bitwarden-sm':

```bash
# Fetch all secrets that the machine account has access to
kamal secrets fetch --adapter bitwarden-sm all

# Fetch secrets from a project
kamal secrets fetch --adapter bitwarden-sm MyProjectID/all

# Extract the secret
kamal secrets extract REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
```

## AWS Secrets Manager

First, install and configure the AWS CLI.

Use the adapter `aws_secrets_manager`:

```bash
# Fetch passwords
kamal secrets fetch --adapter aws_secrets_manager --account default REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from an item
kamal secrets fetch --adapter aws_secrets_manager --account default --from myapp/ REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from multiple items
kamal secrets fetch --adapter aws_secrets_manager --account default myapp/REGISTRY_PASSWORD myapp/DB_PASSWORD

# Extract the secret
kamal secrets extract REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
kamal secrets extract MyItem/REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
```

**Note:** The `--account` option should be set to your AWS CLI profile name, which is typically `default`. Ensure that your AWS CLI is configured with the necessary permissions to access AWS Secrets Manager.

## Doppler

First, install and configure the Doppler CLI.

Use the adapter `doppler`:

```bash
# Fetch passwords
kamal secrets fetch --adapter doppler --from my-project/prd REGISTRY_PASSWORD DB_PASSWORD

# The project/config pattern is also supported in this way
kamal secrets fetch --adapter doppler my-project/prd/REGISTRY_PASSWORD my-project/prd/DB_PASSWORD

# Extract the secret
kamal secrets extract REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
kamal secrets extract DB_PASSWORD <SECRETS-FETCH-OUTPUT>
```

Doppler organizes secrets in "projects" (like `my-awesome-project`) and "configs" (like `prod`, `stg`, etc), use the pattern `project/config` when defining the `--from` option.

The doppler adapter does not use the `--account` option, if given it will be ignored.

## GCP Secret Manager

First, install and configure the gcloud CLI.

The `--account` flag selects an account configured in `gcloud`, and the `--from` flag specifies the **GCP project ID** to be used. The string `default` can be used with the `--account` and `--from` flags to use `gcloud`'s default credentials and project, respectively.

Use the adapter `gcp`:

```bash
# Fetch a secret with an explicit project name, credentials, and secret version:
kamal secrets fetch --adapter=gcp --account=default --from=default my-secret/latest

# The project name can be added as a prefix to the secret name instead of using --from:
kamal secrets fetch --adapter=gcp --account=default default/my-secret/latest

# The 'latest' version is used by default, so it can be omitted as well:
kamal secrets fetch --adapter=gcp --account=default default/my-secret

# If the default project is used, the prefix can also be left out entirely, leading to the simplest
# way to fetch a secret using the default project and credentials, and the latest version of the
# secret:
kamal secrets fetch --adapter=gcp --account=default my-secret

# Multiple secrets can be fetched at the same time.
# Fetch `my-secret` and `another-secret` from the project `my-project`:
kamal secrets fetch --adapter=gcp \
  --account=default \
  --from=my-project \
  my-secret another-secret

# Secrets can be fetched from multiple projects at the same time.
# Fetch from multiple projects, using default to refer to the default project:
kamal secrets fetch --adapter=gcp \
  --account=default \
  default/my-secret my-project/another-secret

# Specific secret versions can be fetched.
# Fetch version 123 of the secret `my-secret` in the default project (the default behavior is to
# fetch `latest`)
kamal secrets fetch --adapter=gcp \
  --account=default \
  default/my-secret/123

# Credentials other than the default can also be used.
# Fetch a secret using the `user@example.com` credentials:
kamal secrets fetch --adapter=gcp \
  --account=user@example.com \
  my-secret

# Service account impersonation and delegation chains are available.
# Fetch a secret as `user@example.com`, impersonating `service-account@example.com` with
# `delegate@example.com` as a delegate
kamal secrets fetch --adapter=gcp \
  --account="user@example.com|delegate@example.com,service-account@example.com" \
  my-secret
```

## Passbolt

First, install and configure the Passbolt CLI.

Passbolt organizes secrets in folders (like `coolfolder`) and these folders can be nested (like `coolfolder/prod`, `coolfolder/stg`, etc). You can access secrets in these folders in two ways:

1. Using the `--from` option to specify the folder path `--from coolfolder`
2. Prefixing the secret names with the folder path `coolfolder/REGISTRY_PASSWORD`

Use the adapter `passbolt`:

```bash
# Fetch passwords from root (no folder)
kamal secrets fetch --adapter passbolt REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from a folder using --from
kamal secrets fetch --adapter passbolt --from coolfolder REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords from a nested folder using --from
kamal secrets fetch --adapter passbolt --from coolfolder/subfolder REGISTRY_PASSWORD DB_PASSWORD

# Fetch passwords by prefixing the folder path to the secret name
kamal secrets fetch --adapter passbolt coolfolder/REGISTRY_PASSWORD coolfolder/DB_PASSWORD

# Fetch passwords from multiple folders
kamal secrets fetch --adapter passbolt coolfolder/REGISTRY_PASSWORD otherfolder/DB_PASSWORD

# Extract the secret values
kamal secrets extract REGISTRY_PASSWORD <SECRETS-FETCH-OUTPUT>
kamal secrets extract DB_PASSWORD <SECRETS-FETCH-OUTPUT>
```

The passbolt adapter does not use the `--account` option, if given it will be ignored.

# details.md

# kamal details

Shows details of all your containers.

```bash
$ kamal details -q
Traefik Host: server2
CONTAINER ID   IMAGE                         COMMAND                  CREATED          STATUS          PORTS                NAMES
b220af815ea7   registry:4443/traefik:v2.10   "/entrypoint.sh --pr…"   52 minutes ago   Up 52 minutes   0.0.0.0:80->80/tcp   traefik

Traefik Host: server1
CONTAINER ID   IMAGE                         COMMAND                  CREATED          STATUS          PORTS                NAMES
e0abb837120a   registry:4443/traefik:v2.10   "/entrypoint.sh --pr…"   52 minutes ago   Up 52 minutes   0.0.0.0:80->80/tcp   traefik

App Host: server2
CONTAINER ID   IMAGE                                                        COMMAND                  CREATED          STATUS                    PORTS     NAMES
3ec7c8122988   registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac   "/docker-entrypoint.…"   52 minutes ago   Up 52 minutes (healthy)   80/tcp    app-web-75bf6fa40b975cbd8aec05abf7164e0982f185ac

App Host: server1
CONTAINER ID   IMAGE                                                        COMMAND                  CREATED          STATUS                    PORTS     NAMES
32ae39c98b29   registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac   "/docker-entrypoint.…"   52 minutes ago   Up 52 minutes (healthy)   80/tcp    app-web-75bf6fa40b975cbd8aec05abf7164e0982f185ac

App Host: server3
CONTAINER ID   IMAGE                                                        COMMAND                  CREATED          STATUS          PORTS     NAMES
df8990876d14   registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac   "/docker-entrypoint.…"   52 minutes ago   Up 52 minutes   80/tcp    app-workers-75bf6fa40b975cbd8aec05abf7164e0982f185ac

CONTAINER ID   IMAGE                          COMMAND                   CREATED          STATUS          PORTS     NAMES
14857a6cb6b1   registry:4443/busybox:1.36.0   "sh -c 'echo \"Starti…"   42 minutes ago   Up 42 minutes             custom-busybox
CONTAINER ID   IMAGE                          COMMAND                   CREATED          STATUS          PORTS     NAMES
17f3ff88ff9f   registry:4443/busybox:1.36.0   "sh -c 'echo \"Starti…"   42 minutes ago   Up 42 minutes             custom-busybox
```

# setup.md

# kamal setup

Kamal setup will run everything required to deploy an application to a fresh host.

It will:

1. Install Docker on all servers, if it has permission and it is not already installed.
2. Boot all accessories.
3. Deploy the app (see `kamal deploy`).

# help.md

# kamal help

Displays help messages. Run `kamal help [command]` for details on a specific command.

```bash
$ kamal help
  kamal accessory           # Manage accessories (db/redis/search)
  kamal app                 # Manage application
  kamal audit               # Show audit log from servers
  kamal build               # Build application image
  kamal config              # Show combined config (including secrets!)
  kamal deploy              # Deploy app to servers
  kamal details             # Show details about all containers
  kamal docs [SECTION]      # Show Kamal configuration documentation
  kamal help [COMMAND]      # Describe available commands or one specific command
  kamal init                # Create config stub in config/deploy.yml and secrets stub in .kamal
  kamal lock                # Manage the deploy lock
  kamal proxy               # Manage kamal-proxy
  kamal prune               # Prune old application images and containers
  kamal redeploy            # Deploy app to servers without bootstrapping servers, starting kamal-proxy, pruning, and registry login
  kamal registry            # Login and -out of the image registry
  kamal remove              # Remove kamal-proxy, app, accessories, and registry session from servers
  kamal rollback [VERSION]  # Rollback app to VERSION
  kamal secrets             # Helpers for extracting secrets
  kamal server              # Bootstrap servers with curl and Docker
  kamal setup               # Setup all accessories, push the env, and deploy app to servers
  kamal upgrade             # Upgrade from Kamal 1.x to 2.0
  kamal version             # Show Kamal version

Options:
  -v, [--verbose], [--no-verbose], [--skip-verbose]  # Detailed logging
  -q, [--quiet], [--no-quiet], [--skip-quiet]        # Minimal logging
      [--version=VERSION]                            # Run commands against a specific app version
  -p, [--primary], [--no-primary], [--skip-primary]  # Run commands only on primary host instead of all
  -h, [--hosts=HOSTS]                                # Run commands on these hosts instead of all (separate by comma, supports wildcards with *)
  -r, [--roles=ROLES]                                # Run commands on these roles instead of all (separate by comma, supports wildcards with *)
  -c, [--config-file=CONFIG_FILE]                    # Path to config file
                                                     # Default: config/deploy.yml
  -d, [--destination=DESTINATION]                    # Specify destination to be used for config file (staging -> deploy.staging.yml)
  -H, [--skip-hooks]                                 # Don't run hooks
                                                     # Default: false
```

# init.md

# kamal init

Creates the files needed to deploy your application with `kamal`.

```bash
$ kamal init
Created configuration file in config/deploy.yml
Created .kamal/secrets file
Created sample hooks in .kamal/hooks
```

# audit.md

# kamal audit

Show the latest commands that have been run on each server.

```bash
$ kamal audit
 kamal audit
  INFO [1ec52bf7] Running /usr/bin/env tail -n 50 .kamal/app-audit.log on server2
  INFO [54911c10] Running /usr/bin/env tail -n 50 .kamal/app-audit.log on server1
  INFO [2f3d32d0] Running /usr/bin/env tail -n 50 .kamal/app-audit.log on server3
  INFO [2f3d32d0] Finished in 0.232 seconds with exit status 0 (successful).
App Host: server3
[2024-04-05T07:14:23Z] [user] Pushed env files
[2024-04-05T07:14:29Z] [user] Pulled image with version 75bf6fa40b975cbd8aec05abf7164e0982f185ac
[2024-04-05T07:14:45Z] [user] [workers] Booted app version 75bf6fa40b975cbd8aec05abf7164e0982f185ac
[2024-04-05T07:14:53Z] [user] Tagging registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac as the latest image
[2024-04-05T07:14:53Z] [user] Pruned containers
[2024-04-05T07:14:53Z] [user] Pruned images

  INFO [54911c10] Finished in 0.232 seconds with exit status 0 (successful).
App Host: server1
[2024-04-05T07:14:23Z] [user] Pushed env files
[2024-04-05T07:14:29Z] [user] Pulled image with version 75bf6fa40b975cbd8aec05abf7164e0982f185ac
[2024-04-05T07:14:45Z] [user] [web] Booted app version 75bf6fa40b975cbd8aec05abf7164e0982f185ac
[2024-04-05T07:14:53Z] [user] Tagging registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac as the latest image
[2024-04-05T07:14:53Z] [user] Pruned containers
[2024-04-05T07:14:53Z] [user] Pruned images

  INFO [1ec52bf7] Finished in 0.233 seconds with exit status 0 (successful).
App Host: server2
[2024-04-05T07:14:23Z] [user] Pushed env files
[2024-04-05T07:14:29Z] [user] Pulled image with version 75bf6fa40b975cbd8aec05abf7164e0982f185ac
[2024-04-05T07:14:45Z] [user] [web] Booted app version 75bf6fa40b975cbd8aec05abf7164e0982f185ac
[2024-04-05T07:14:53Z] [user] Tagging registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac as the latest image
[2024-04-05T07:14:53Z] [user] Pruned containers
[2024-04-05T07:14:53Z] [user] Pruned images
```

# config.md

# kamal config

Displays your config.

```bash
$ kamal config
---
:roles:
- web
:hosts:
- vm1
- vm2
:primary_host: vm1
:version: 505f4f60089b262c693885596fbd768a6ab663e9
:repository: registry:4443/app
:absolute_image: registry:4443/app:505f4f60089b262c693885596fbd768a6ab663e9
:service_with_version: app-505f4f60089b262c693885596fbd768a6ab663e9
:volume_args: []
:ssh_options:
  :user: root
  :port: 22
  :keepalive: true
  :keepalive_interval: 30
  :log_level: :fatal
:sshkit: {}
:builder:
  driver: docker
  arch: arm64
  args:
    COMMIT_SHA: 505f4f60089b262c693885596fbd768a6ab663e9
:accessories:
  busybox:
    service: custom-busybox
    image: registry:4443/busybox:1.36.0
    cmd: sh -c 'echo "Starting busybox..."; trap exit term; while true; do sleep 1;
      done'
    roles:
    - web
:logging:
- "--log-opt"
- max-size="10m"
```

# deploy.md

# kamal deploy

Build and deploy your app to all servers. By default, it will build the currently checked out version of the app.

Kamal will use kamal-proxy to seamlessly move requests from the old version of the app to the new one without downtime.

The deployment process is:

1. Log in to the Docker registry locally and on all servers.
2. Build the app image, push it to the registry, and pull it onto the servers.
3. Ensure kamal-proxy is running and accepting traffic on ports 80 and 443.
4. Start a new container with the version of the app that matches the current Git version hash.
5. Tell kamal-proxy to route traffic to the new container once it is responding with `200 OK` to `GET /up`.
6. Stop the old container running the previous version of the app.
7. Prune unused images and stopped containers to ensure servers don't fill up.

```bash
Usage:
  kamal deploy

Options:
  -P, [--skip-push]                                  # Skip image build and push
                                                     # Default: false
  -v, [--verbose], [--no-verbose], [--skip-verbose]  # Detailed logging
  -q, [--quiet], [--no-quiet], [--skip-quiet]        # Minimal logging
      [--version=VERSION]                            # Run commands against a specific app version
  -p, [--primary], [--no-primary], [--skip-primary]  # Run commands only on primary host instead of all
  -h, [--hosts=HOSTS]                                # Run commands on these hosts instead of all (separate by comma, supports wildcards with *)
  -r, [--roles=ROLES]                                # Run commands on these roles instead of all (separate by comma, supports wildcards with *)
  -c, [--config-file=CONFIG_FILE]                    # Path to config file
                                                     # Default: config/deploy.yml
  -d, [--destination=DESTINATION]                    # Specify destination to be used for config file (staging -> deploy.staging.yml)
  -H, [--skip-hooks]                                 # Don't run hooks
                                                     # Default: false
```

# version.md

# kamal version

Returns the version of Kamal you have installed.

```bash
$ kamal version
2.7.0
```

# index.md

# build.md

# kamal build

Build your app images and push them to your servers. These commands are called indirectly by `kamal deploy` and `kamal redeploy`.

By default, Kamal will only build files you have committed to your Git repository. However, you can configure Kamal to use the current context (instead of a Git archive of HEAD) by setting the build context.

```bash
$ kamal build
Commands:
  kamal build create          # Create a build setup
  kamal build deliver         # Build app and push app image to registry then pull image on servers
  kamal build details         # Show build setup
  kamal build dev             # Build using the working directory, tag it as dirty, and push to local image store.
  kamal build help [COMMAND]  # Describe subcommands or one specific subcommand
  kamal build pull            # Pull app image from registry onto servers
  kamal build push            # Build and push app image to registry
  kamal build remove          # Remove build setup
```

The `build dev` and `build push` commands also support an `--output` option which specifies where the image should be pushed. `build push` defaults to "registry", and `build dev` defaults to "docker" which is the local image store. Any exported type supported by the `docker buildx build` option `--output` is allowed.

Examples:

```bash
$ kamal build push
Running the pre-connect hook...
  INFO [92ebc200] Running /usr/bin/env .kamal/hooks/pre-connect on localhost
  INFO [92ebc200] Finished in 0.004 seconds with exit status 0 (successful).
  INFO [cbbad07e] Running /usr/bin/env mkdir -p .kamal on server1
  INFO [e6ac30e7] Running /usr/bin/env mkdir -p .kamal on server3
  INFO [a1adae3a] Running /usr/bin/env mkdir -p .kamal on server2
  INFO [cbbad07e] Finished in 0.145 seconds with exit status 0 (successful).
  INFO [a1adae3a] Finished in 0.179 seconds with exit status 0 (successful).
  INFO [e6ac30e7] Finished in 0.182 seconds with exit status 0 (successful).
  INFO [c6242009] Running /usr/bin/env mkdir -p .kamal/locks on server1
  INFO [c6242009] Finished in 0.009 seconds with exit status 0 (successful).
Acquiring the deploy lock...
  INFO [427ae9bc] Running docker --version on localhost
  INFO [427ae9bc] Finished in 0.039 seconds with exit status 0 (successful).
Running the pre-build hook...
  INFO [2f120630] Running /usr/bin/env .kamal/hooks/pre-build on localhost
  INFO [2f120630] Finished in 0.004 seconds with exit status 0 (successful).
  INFO [ad386911] Running /usr/bin/env git archive --format=tar HEAD | docker build -t registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac -t registry:4443/app:latest --label service="app" --build-arg [REDACTED] --file Dockerfile - && docker push registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac && docker push registry:4443/app:latest on localhost
 DEBUG [ad386911] Command: /usr/bin/env git archive --format=tar HEAD | docker build -t registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac -t registry:4443/app:latest --label service="app" --build-arg [REDACTED] --file Dockerfile - && docker push registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac && docker push registry:4443/app:latest
 DEBUG [ad386911] 	#0 building with "default" instance using docker driver
 DEBUG [ad386911]
 DEBUG [ad386911] 	#1 [internal] load remote build context
 DEBUG [ad386911] 	#1 CACHED
 DEBUG [ad386911]
 DEBUG [ad386911] 	#2 copy /context /
 DEBUG [ad386911] 	#2 CACHED
 DEBUG [ad386911]
 DEBUG [ad386911] 	#3 [internal] load metadata for registry:4443/nginx:1-alpine-slim
 DEBUG [ad386911] 	#3 DONE 0.0s
 DEBUG [ad386911]
 DEBUG [ad386911] 	#4 [1/5] FROM registry:4443/nginx:1-alpine-slim@sha256:558cdef0693faaa02c0b81c21b5d6f4b4fe24e3ac747581f3e6e8f5c4032db58
 DEBUG [ad386911] 	#4 DONE 0.0s
 DEBUG [ad386911]
 DEBUG [ad386911] 	#5 [4/5] RUN mkdir -p /usr/share/nginx/html/versions && echo "version" > /usr/share/nginx/html/versions/75bf6fa40b975cbd8aec05abf7164e0982f185ac
 DEBUG [ad386911] 	#5 CACHED
 DEBUG [ad386911]
 DEBUG [ad386911] 	#6 [2/5] COPY default.conf /etc/nginx/conf.d/default.conf
 DEBUG [ad386911] 	#6 CACHED
 DEBUG [ad386911]
 DEBUG [ad386911] 	#7 [3/5] RUN echo 75bf6fa40b975cbd8aec05abf7164e0982f185ac > /usr/share/nginx/html/version
 DEBUG [ad386911] 	#7 CACHED
 DEBUG [ad386911]
 DEBUG [ad386911] 	#8 [5/5] RUN mkdir -p /usr/share/nginx/html/versions && echo "hidden" > /usr/share/nginx/html/versions/.hidden
 DEBUG [ad386911] 	#8 CACHED
 DEBUG [ad386911]
 DEBUG [ad386911] 	#9 exporting to image
 DEBUG [ad386911] 	#9 exporting layers done
 DEBUG [ad386911] 	#9 writing image sha256:ed9205d697e5f9f735e84e341a19a3d379b9b4a8dc5d04b6219bda29e6126489 done
 DEBUG [ad386911] 	#9 naming to registry:4443/app:75bf6fa40b975cbd8aec05abf7164e0982f185ac done
 DEBUG [ad386911] 	#9 naming to registry:4443/app:latest done
 DEBUG [ad386911] 	#9 DONE 0.0s
 DEBUG [ad386911] 	The push refers to repository [registry:4443/app]
 DEBUG [ad386911] 	7e49189613ab: Preparing
 DEBUG [ad386911] 	054c18a8e0a6: Preparing
 DEBUG [ad386911] 	1552c04abfaa: Preparing
 DEBUG [ad386911] 	36f2f66132ea: Preparing
 DEBUG [ad386911] 	d5e2fb5f3301: Preparing
 DEBUG [ad386911] 	8fde05710e93: Preparing
 DEBUG [ad386911] 	fdf572380e92: Preparing
 DEBUG [ad386911] 	a031a04401d0: Preparing
 DEBUG [ad386911] 	ecb78d985cad: Preparing
 DEBUG [ad386911] 	3e0e830ccd77: Preparing
 DEBUG [ad386911] 	7c504f21be85: Preparing
 DEBUG [ad386911] 	fdf572380e92: Waiting
 DEBUG [ad386911] 	a031a04401d0: Waiting
 DEBUG [ad386911] 	ecb78d985cad: Waiting
 DEBUG [ad386911] 	3e0e830ccd77: Waiting
 DEBUG [ad386911] 	7c504f21be85: Waiting
 DEBUG [ad386911] 	8fde05710e93: Waiting
 DEBUG [ad386911] 	054c18a8e0a6: Layer already exists
 DEBUG [ad386911] 	7e49189613ab: Layer already exists
 DEBUG [ad386911] 	36f2f66132ea: Layer already exists
 DEBUG [ad386911] 	d5e2fb5f3301: Layer already exists
 DEBUG [ad386911] 	1552c04abfaa: Layer already exists
 DEBUG [ad386911] 	8fde05710e93: Layer already exists
 DEBUG [ad386911] 	fdf572380e92: Layer already exists
 DEBUG [ad386911] 	a031a04401d0: Layer already exists
 DEBUG [ad386911] 	3e0e830ccd77: Layer already exists
 DEBUG [ad386911] 	ecb78d985cad: Layer already exists
 DEBUG [ad386911] 	7c504f21be85: Layer already exists
 DEBUG [ad386911] 	75bf6fa40b975cbd8aec05abf7164e0982f185ac: digest: sha256:68e534dab98fc7c65c8e2353f6414e9c6c812481deea8d57ae6b0b0140ec40d5 size: 2604
 DEBUG [ad386911] 	The push refers to repository [registry:4443/app]
 DEBUG [ad386911] 	7e49189613ab: Preparing
 DEBUG [ad386911] 	054c18a8e0a6: Preparing
 DEBUG [ad386911] 	1552c04abfaa: Preparing
 DEBUG [ad386911] 	36f2f66132ea: Preparing
 DEBUG [ad386911] 	d5e2fb5f3301: Preparing
 DEBUG [ad386911] 	8fde05710e93: Preparing
 DEBUG [ad386911] 	fdf572380e92: Preparing
 DEBUG [ad386911] 	a031a04401d0: Preparing
 DEBUG [ad386911] 	ecb78d985cad: Preparing
 DEBUG [ad386911] 	3e0e830ccd77: Preparing
 DEBUG [ad386911] 	7c504f21be85: Preparing
 DEBUG [ad386911] 	fdf572380e92: Waiting
 DEBUG [ad386911] 	a031a04401d0: Waiting
 DEBUG [ad386911] 	ecb78d985cad: Waiting
 DEBUG [ad386911] 	3e0e830ccd77: Waiting
 DEBUG [ad386911] 	7c504f21be85: Waiting
 DEBUG [ad386911] 	8fde05710e93: Waiting
 DEBUG [ad386911] 	36f2f66132ea: Layer already exists
 DEBUG [ad386911] 	7e49189613ab: Layer already exists
 DEBUG [ad386911] 	054c18a8e0a6: Layer already exists
 DEBUG [ad386911] 	1552c04abfaa: Layer already exists
 DEBUG [ad386911] 	d5e2fb5f3301: Layer already exists
 DEBUG [ad386911] 	8fde05710e93: Layer already exists
 DEBUG [ad386911] 	fdf572380e92: Layer already exists
 DEBUG [ad386911] 	a031a04401d0: Layer already exists
 DEBUG [ad386911] 	ecb78d985cad: Layer already exists
 DEBUG [ad386911] 	3e0e830ccd77: Layer already exists
 DEBUG [ad386911] 	7c504f21be85: Layer already exists
 DEBUG [ad386911] 	latest: digest: sha256:68e534dab98fc7c65c8e2353f6414e9c6c812481deea8d57ae6b0b0140ec40d5 size: 2604
  INFO [ad386911] Finished in 0.502 seconds with exit status 0 (successful).
Releasing the deploy lock...
```

# server.md

# kamal server

```bash
$ kamal server
Commands:
  kamal server bootstrap       # Set up Docker to run Kamal apps
  kamal server exec            # Run a custom command on the server (use --help to show options)
  kamal server help [COMMAND]  # Describe subcommands or one specific subcommand
```

## Bootstrap server

You can run `kamal server bootstrap` to set up Docker on your hosts.

It will check if Docker is installed and, if not, it will attempt to install it via get.docker.com.

```bash
$ kamal server bootstrap
```

## Execute command on all servers

Run a custom command on all servers.

```bash
$ kamal server exec "date"
Running 'date' on 867.53.0.9...
  INFO [e79c62bb] Running /usr/bin/env date on 867.53.0.9
  INFO [e79c62bb] Finished in 0.247 seconds with exit status 0 (successful).
App Host: 867.53.0.9
Thu Jun 13 08:06:19 AM UTC 2024
```

## Execute command on primary server

Run a custom command on the primary server.

```bash
$ kamal server exec --primary "date"
Running 'date' on 867.53.0.9...
  INFO [8bbeb21a] Running /usr/bin/env date on 867.53.0.9
  INFO [8bbeb21a] Finished in 0.265 seconds with exit status 0 (successful).
App Host: 867.53.0.9
Thu Jun 13 08:07:09 AM UTC 2024
```

## Execute interactive command on server

Run an interactive command on the server.

```bash
$ kamal server exec --interactive "/bin/bash"
Running '/bin/bash' on 867.53.0.9 interactively...
root@server:~#
```

# rollback.md

# kamal rollback

You can rollback a deployment with `kamal rollback`.

If you've discovered a bad deploy, you can quickly rollback to a previous image. You can see what old containers are available for rollback by running `kamal app containers -q`. It'll give you a presentation similar to `kamal app details`, but include all the old containers as well.

```
App Host: 192.168.0.1
CONTAINER ID   IMAGE                                                                         COMMAND                    CREATED          STATUS                      PORTS      NAMES
1d3c91ed1f51   registry.digitalocean.com/user/app:6ef8a6a84c525b123c5245345a8483f86d05a123   "/rails/bin/docker-e..."   19 minutes ago   Up 19 minutes               3000/tcp   chat-6ef8a6a84c525b123c5245345a8483f86d05a123
539f26b28369   registry.digitalocean.com/user/app:e5d9d7c2b898289dfbc5f7f1334140d984eedae4   "/rails/bin/docker-e..."   31 minutes ago   Exited (1) 27 minutes ago              chat-e5d9d7c2b898289dfbc5f7f1334140d984eedae4

App Host: 192.168.0.2
CONTAINER ID   IMAGE                                                                         COMMAND                    CREATED          STATUS                      PORTS      NAMES
badb1aa51db4   registry.digitalocean.com/user/app:6ef8a6a84c525b123c5245345a8483f86d05a123   "/rails/bin/docker-e..."   19 minutes ago   Up 19 minutes               3000/tcp   chat-6ef8a6a84c525b123c5245345a8483f86d05a123
6f170d1172ae   registry.digitalocean.com/user/app:e5d9d7c2b898289dfbc5f7f1334140d984eedae4   "/rails/bin/docker-e..."   31 minutes ago   Exited (1) 27 minutes ago              chat-e5d9d7c2b898289dfbc5f7f1334140d984eedae4
```

From the example above, we can see that `e5d9d7c2b898289dfbc5f7f1334140d984eedae4` was the last version, so it's available as a rollback target. We can perform this rollback by running `kamal rollback e5d9d7c2b898289dfbc5f7f1334140d984eedae4`.

That'll stop `6ef8a6a84c525b123c5245345a8483f86d05a123` and then start a new container running the same image as `e5d9d7c2b898289dfbc5f7f1334140d984eedae4`. Nothing needs to be downloaded from the registry.

**Note:** By default, old containers are pruned after 3 days when you run `kamal deploy`.

# accessory.md

# kamal accessory

Accessories are long-lived services that your app depends on. They are not updated when you deploy.

They are not proxied, so rebooting will have a small period of downtime. You can map volumes from the host server into your container for persistence across reboots.

Run `kamal accessory` to view and manage your accessories.

```bash
$ kamal accessory
Commands:
  kamal accessory boot [NAME]           # Boot new accessory service on host (use NAME=all to boot all accessories)
  kamal accessory details [NAME]        # Show details about accessory on host (use NAME=all to show all accessories)
  kamal accessory exec [NAME] [CMD...]  # Execute a custom command on servers within the accessory container (use --help to show options)
  kamal accessory help [COMMAND]        # Describe subcommands or one specific subcommand
  kamal accessory logs [NAME]           # Show log lines from accessory on host (use --help to show options)
  kamal accessory reboot [NAME]         # Reboot existing accessory on host (stop container, remove container, start new container; use NAME=all to boot all accessories)
  kamal accessory remove [NAME]         # Remove accessory container, image and data directory from host (use NAME=all to remove all accessories)
  kamal accessory restart [NAME]        # Restart existing accessory container on host
  kamal accessory start [NAME]          # Start existing accessory container on host
  kamal accessory stop [NAME]           # Stop existing accessory container on host
  kamal accessory upgrade               # Upgrade accessories from Kamal 1.x to 2.0 (restart them in 'kamal' network)
```

To update an accessory, update the image in your config and run `kamal accessory reboot [NAME]`.

Example:

```bash
$ kamal accessory boot all
Running the pre-connect hook...
  INFO [bd04b11b] Running /usr/bin/env .kamal/hooks/pre-connect on localhost
  INFO [bd04b11b] Finished in 0.003 seconds with exit status 0 (successful).
  INFO [681a028b] Running /usr/bin/env mkdir -p .kamal on server2
  INFO [e3495d1d] Running /usr/bin/env mkdir -p .kamal on server1
  INFO [e7c5c159] Running /usr/bin/env mkdir -p .kamal on server3
  INFO [e3495d1d] Finished in 0.170 seconds with exit status 0 (successful).
  INFO [681a028b] Finished in 0.182 seconds with exit status 0 (successful).
  INFO [e7c5c159] Finished in 0.185 seconds with exit status 0 (successful).
  INFO [83153af3] Running /usr/bin/env mkdir -p .kamal/locks on server1
  INFO [83153af3] Finished in 0.028 seconds with exit status 0 (successful).
Acquiring the deploy lock...
  INFO [416a654c] Running docker login registry:4443 -u [REDACTED] -p [REDACTED] on server1
  INFO [3fb56559] Running docker login registry:4443 -u [REDACTED] -p [REDACTED] on server2
  INFO [3fb56559] Finished in 0.065 seconds with exit status 0 (successful).
  INFO [416a654c] Finished in 0.080 seconds with exit status 0 (successful).
  INFO [2705083f] Running docker run --name custom-busybox --detach --restart unless-stopped --log-opt max-size="10m" --env-file .kamal/env/accessories/custom-busybox.env --label service="custom-busybox" registry:4443/busybox:1.36.0 sh -c 'echo "Starting busybox..."; trap exit term; while true; do sleep 1; done' on server2
  INFO [3cb3adb6] Running docker run --name custom-busybox --detach --restart unless-stopped --log-opt max-size="10m" --env-file .kamal/env/accessories/custom-busybox.env --label service="custom-busybox" registry:4443/busybox:1.36.0 sh -c 'echo "Starting busybox..."; trap exit term; while true; do sleep 1; done' on server1
  INFO [3cb3adb6] Finished in 0.552 seconds with exit status 0 (successful).
  INFO [2705083f] Finished in 0.566 seconds with exit status 0 (successful).
Releasing the deploy lock...
```

# docs.md

# kamal docs

Outputs configuration documentation.

# upgrade.md

# kamal upgrade

Use `kamal upgrade` to upgrade your app running under Kamal 1.x to Kamal 2.0.

Please read the Upgrade Guide first.

# proxy.md

# kamal proxy

Kamal uses kamal-proxy to proxy requests to the application containers, allowing us to have zero-downtime deployments.

```bash
$ kamal proxy
Commands:
  kamal proxy boot                         # Boot proxy on servers
  kamal proxy boot_config <set|get|reset>  # Manage kamal-proxy boot configuration
  kamal proxy details                      # Show details about proxy container from servers
  kamal proxy help [COMMAND]               # Describe subcommands or one specific subcommand
  kamal proxy logs                         # Show log lines from proxy on servers
  kamal proxy reboot                       # Reboot proxy on servers (stop container, remove container, start new container)
  kamal proxy remove                       # Remove proxy container and image from servers
  kamal proxy restart                      # Restart existing proxy container on servers
  kamal proxy start                        # Start existing proxy container on servers
  kamal proxy stop                         # Stop existing proxy container on servers
```

When you want to upgrade kamal-proxy, you can call `kamal proxy reboot`. This is going to cause a small outage on each server and will prompt for confirmation.

You can use a rolling reboot with `kamal proxy reboot --rolling` to avoid restarting on all servers simultaneously.

You can also use pre-proxy-reboot and post-proxy-reboot hooks to remove and add the servers to upstream load balancers as you reboot them.

## Boot configuration

You can manage boot configuration for kamal-proxy with `kamal proxy boot_config`.

```bash
$ kamal proxy boot_config
Commands:
  kamal proxy boot_config set [OPTIONS]
  kamal proxy boot_config get
  kamal proxy boot_config reset

Options for 'set':
      [--publish], [--no-publish], [--skip-publish]   # Publish the proxy ports on the host
                                                      # Default: true
      [--http-port=N]                                 # HTTP port to publish on the host
                                                      # Default: 80
      [--https-port=N]                                # HTTPS port to publish on the host
                                                      # Default: 443
      [--log-max-size=LOG_MAX_SIZE]                   # Max size of proxy logs
                                                      # Default: 10m
      [--docker-options=option=value option2=value2]  # Docker options to pass to the proxy container
```

When set, the config will be stored on the server the proxy runs on.

If you are running more than one application on a single server, there is only one proxy, and the boot config is shared, so you'll need to manage it centrally.

The configuration will be loaded at boot time when calling `kamal proxy boot` or `kamal proxy reboot`.

# registry.md

# kamal registry

Log in and out of the Docker registry on your servers.

```bash
$ kamal registry
Commands:
  kamal registry help [COMMAND]  # Describe subcommands or one specific subcommand
  kamal registry login           # Log in to registry locally and remotely
  kamal registry logout          # Log out of registry locally and remotely
```

Examples:

```bash
$ kamal registry login
  INFO [60171eef] Running docker login registry:4443 -u [REDACTED] -p [REDACTED] on localhost
  INFO [60171eef] Finished in 0.069 seconds with exit status 0 (successful).
  INFO [427368d0] Running docker login registry:4443 -u [REDACTED] -p [REDACTED] on server1
  INFO [4c4ab467] Running docker login registry:4443 -u [REDACTED] -p [REDACTED] on server3
  INFO [f985bed4] Running docker login registry:4443 -u [REDACTED] -p [REDACTED] on server2
  INFO [427368d0] Finished in 0.232 seconds with exit status 0 (successful).
  INFO [f985bed4] Finished in 0.234 seconds with exit status 0 (successful).
  INFO [4c4ab467] Finished in 0.245 seconds with exit status 0 (successful).
$ kamal registry logout
  INFO [72b94e74] Running docker logout registry:4443 on server2
  INFO [d096054d] Running docker logout registry:4443 on server1
  INFO [8488da90] Running docker logout registry:4443 on server3
  INFO [72b94e74] Finished in 0.142 seconds with exit status 0 (successful).
  INFO [8488da90] Finished in 0.179 seconds with exit status 0 (successful).
  INFO [d096054d] Finished in 0.183 seconds with exit status 0 (successful).
```

# remove.md

# kamal remove

This will remove the app, kamal-proxy, and accessory containers and log out of the Docker registry.

It will prompt for confirmation unless you add the `-y` option.

# view-all-commands.md

# View all commands

You can view all of the commands by running `kamal --help`.

```bash
$ kamal --help
Commands:
  kamal accessory           # Manage accessories (db/redis/search)
  kamal app                 # Manage application
  kamal audit               # Show audit log from servers
  kamal build               # Build application image
  kamal config              # Show combined config (including secrets!)
  kamal deploy              # Deploy app to servers
  kamal details             # Show details about all containers
  kamal docs [SECTION]      # Show Kamal configuration documentation
  kamal help [COMMAND]      # Describe available commands or one specific command
  kamal init                # Create config stub in config/deploy.yml and secrets stub in .kamal
  kamal lock                # Manage the deploy lock
  kamal proxy               # Manage kamal-proxy
  kamal prune               # Prune old application images and containers
  kamal redeploy            # Deploy app to servers without bootstrapping servers, starting kamal-proxy, pruning, and registry login
  kamal registry            # Login and -out of the image registry
  kamal remove              # Remove kamal-proxy, app, accessories, and registry session from servers
  kamal rollback [VERSION]  # Rollback app to VERSION
  kamal secrets             # Helpers for extracting secrets
  kamal server              # Bootstrap servers with curl and Docker
  kamal setup               # Setup all accessories, push the env, and deploy app to servers
  kamal upgrade             # Upgrade from Kamal 1.x to 2.0
  kamal version             # Show Kamal version

Options:
  -v, [--verbose], [--no-verbose], [--skip-verbose]  # Detailed logging
  -q, [--quiet], [--no-quiet], [--skip-quiet]        # Minimal logging
      [--version=VERSION]                            # Run commands against a specific app version
  -p, [--primary], [--no-primary], [--skip-primary]  # Run commands only on primary host instead of all
  -h, [--hosts=HOSTS]                                # Run commands on these hosts instead of all (separate by comma, supports wildcards with *)
  -r, [--roles=ROLES]                                # Run commands on these roles instead of all (separate by comma, supports wildcards with *)
  -c, [--config-file=CONFIG_FILE]                    # Path to config file
                                                     # Default: config/deploy.yml
  -d, [--destination=DESTINATION]                    # Specify destination to be used for config file (staging -> deploy.staging.yml)
  -H, [--skip-hooks]                                 # Don't run hooks
                                                     # Default: false
```
