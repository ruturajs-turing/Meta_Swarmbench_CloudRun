.PHONY: up down logs test-api build-web smoke runner-smoke validate-plugin

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=120

test-api:
	docker compose exec api python -m pytest -q

build-web:
	docker compose exec web npm run build

smoke:
	curl -s http://localhost:18080/health

runner-smoke:
	AEGISRUN_HOME=/private/tmp/aegisrun-demo ./cli/runnerctl login --endpoint http://localhost:18080 --user admin --password aegisrun
	AEGISRUN_HOME=/private/tmp/aegisrun-demo ./cli/runnerctl workspace
	AEGISRUN_HOME=/private/tmp/aegisrun-demo ./cli/runnerctl terminal
	printf '0\n' | AEGISRUN_HOME=/private/tmp/aegisrun-demo ./cli/runnerctl tui
	AEGISRUN_HOME=/private/tmp/aegisrun-demo ./cli/runnerctl run examples/sample-task --mode probe --tail

validate-plugin:
	python3 $(HOME)/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
