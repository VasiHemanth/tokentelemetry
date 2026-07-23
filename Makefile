# Auto-select compose tool: podman compose > docker compose
COMPOSE      := $(if $(shell podman compose version 2>/dev/null),podman compose,docker compose)
COMPOSE_PROD := $(COMPOSE) -f compose.yml -f docker-compose.prod.yml
CONTAINER    := $(if $(shell command -v podman 2>/dev/null),podman,docker)
PROJECT    := $(notdir $(CURDIR))
_BUILD_LOG := /tmp/tt-build.log

.DEFAULT_GOAL := help

.PHONY: help up up-detach down build logs ps clean _cleanup up-prod pull

# Shared quiet-build recipe: one-liner status, full log only on failure
define quiet-build
@printf '\033[2mbuilding images...\033[0m '; \
if $(COMPOSE) --progress quiet build > $(_BUILD_LOG) 2>&1; then \
    printf '\033[32m✔\033[0m\n'; \
else \
    printf '\033[31m✘\033[0m\n\n'; cat $(_BUILD_LOG); false; \
fi
endef


define print-urls
@printf '\n\033[1mTokenTelemetry running\033[0m\n'
@printf '  frontend  \033[2m→\033[0m  \033[36mhttp://localhost:%s\033[0m\n' "$${PORT:-13000}"
@printf '  backend   \033[2m→\033[0m  \033[36mhttp://localhost:%s\033[0m\n' "$${TT_API_PORT:-18000}"
@printf '\n'
endef

help: ## Show this help
	@printf '\033[1;37mTokenTelemetry\033[0m \033[2m· container tooling\033[0m\n'
	@printf '\033[2mtool  →\033[0m \033[36m$(COMPOSE)\033[0m\n'
	@awk 'BEGIN{FS=":.*##"} \
		/^##@/{printf "\n\033[1;33m%s\033[0m\n",substr($$0,5)} \
		/^[a-zA-Z_-]+:.*##/{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}' \
		$(MAKEFILE_LIST)
	@printf '\n'

# Stops and removes this project's containers so gvproxy releases their
# port-forward entries before the next `up`.
_cleanup:
	@$(COMPOSE) down --remove-orphans -t 1 2>/dev/null || true
	@if command -v podman >/dev/null 2>&1; then \
	    ids=$$(podman ps -aq --filter label=com.docker.compose.project=$(PROJECT) 2>/dev/null); \
	    [ -n "$$ids" ] && podman rm -f $$ids 2>/dev/null || true; \
	fi

##@ Lifecycle
up: _cleanup ## Start services, building images only if not yet built
	@$(CONTAINER) image inspect $(PROJECT)-backend $(PROJECT)-frontend \
	    >/dev/null 2>&1 || $(MAKE) --no-print-directory build
	$(print-urls)
	@$(COMPOSE) up

up-detach: _cleanup ## Start services in background, building only if needed
	@$(CONTAINER) image inspect $(PROJECT)-backend $(PROJECT)-frontend \
	    >/dev/null 2>&1 || $(MAKE) --no-print-directory build
	@$(COMPOSE) up -d
	$(print-urls)

down: ## Stop and remove containers
	@$(COMPOSE) down

build: ## Build (or rebuild) images without starting
	$(quiet-build)

up-prod: _cleanup ## Pull GHCR images and start in background (production)
	@$(COMPOSE_PROD) pull
	@$(COMPOSE_PROD) up -d
	$(print-urls)

pull: ## Pull latest images from GHCR without starting
	@$(COMPOSE_PROD) pull

##@ Observability
logs: ## Tail logs from all services
	@$(COMPOSE) logs -f

ps: ## Show running services
	@$(COMPOSE) ps

##@ Maintenance
clean: ## Remove containers, local images, and tt_data volume
	@$(COMPOSE) down --rmi local -v

machine-restart: ## Restart Podman machine — clears stale gvproxy port entries
	@printf '\033[2mrestarting Podman machine...\033[0m\n'
	@podman machine stop && podman machine start
	@printf '\033[32m✔\033[0m machine ready\n'
