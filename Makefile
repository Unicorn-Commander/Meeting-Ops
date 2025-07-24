# Makefile for Unicorn Commander

.PHONY: help build up down logs clean dev prod shell test

help:
	@echo "Unicorn Commander - Docker Commands"
	@echo ""
	@echo "Development:"
	@echo "  make dev        - Start development environment"
	@echo "  make build-dev  - Build development images"
	@echo ""
	@echo "Production:"
	@echo "  make prod       - Start production environment"
	@echo "  make build      - Build production images"
	@echo ""
	@echo "Common:"
	@echo "  make up         - Start services (basic)"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View logs"
	@echo "  make clean      - Clean up volumes and images"
	@echo "  make shell-backend  - Shell into backend container"
	@echo "  make shell-frontend - Shell into frontend container"

# Development commands
dev:
	docker-compose -f docker-compose.dev.yml up

build-dev:
	docker-compose -f docker-compose.dev.yml build

# Production commands
prod:
	docker-compose -f docker-compose.prod.yml up -d

build:
	docker-compose -f docker-compose.yml build

build-prod:
	docker-compose -f docker-compose.prod.yml build

# Basic commands
up:
	docker-compose up -d

down:
	docker-compose down
	docker-compose -f docker-compose.dev.yml down
	docker-compose -f docker-compose.prod.yml down

logs:
	docker-compose logs -f

logs-backend:
	docker-compose logs -f backend

logs-frontend:
	docker-compose logs -f frontend

# Shell access
shell-backend:
	docker exec -it unicorn-backend /bin/bash

shell-frontend:
	docker exec -it unicorn-frontend /bin/sh

shell-backend-dev:
	docker exec -it unicorn-backend-dev /bin/bash

# Database
db-shell:
	docker exec -it unicorn-db psql -U unicorn unicorn_commander

db-backup:
	docker exec unicorn-db pg_dump -U unicorn unicorn_commander > backup_`date +%Y%m%d_%H%M%S`.sql

# Cleanup
clean:
	docker-compose down -v
	docker-compose -f docker-compose.dev.yml down -v
	docker-compose -f docker-compose.prod.yml down -v
	docker system prune -f

clean-all:
	docker-compose down -v --rmi all
	docker-compose -f docker-compose.dev.yml down -v --rmi all
	docker-compose -f docker-compose.prod.yml down -v --rmi all
	docker system prune -af

# Testing
test-backend:
	docker exec unicorn-backend pytest

test-frontend:
	docker exec unicorn-frontend npm test

# Quick restart
restart:
	make down
	make up

restart-dev:
	docker-compose -f docker-compose.dev.yml restart

# View running containers
ps:
	docker-compose ps
	docker-compose -f docker-compose.dev.yml ps
	docker-compose -f docker-compose.prod.yml ps