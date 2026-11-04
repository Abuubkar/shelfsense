TAXONOMY_URL := https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt

.PHONY: taxonomy lint test test-int codegen contract-check smoke chaos web web-test golden eval eval-test eval-latency sweep

# Download the official Google Product Taxonomy (with IDs) as data/taxonomy/<version>.txt plus its checksum.
# The version comes from the file's own header. Never fetched at runtime; scripts/load_taxonomy.py reads the file.
taxonomy:
	@mkdir -p data/taxonomy
	curl -fsSL $(TAXONOMY_URL) -o data/taxonomy/download.tmp
	@v=$$(head -1 data/taxonomy/download.tmp | tr -d '\r' | sed -n 's/^# Google_Product_Taxonomy_Version: //p'); \
	test -n "$$v" || { echo "no version header in the download"; exit 1; }; \
	mv data/taxonomy/download.tmp data/taxonomy/$$v.txt; \
	cd data/taxonomy && shasum -a 256 $$v.txt > $$v.txt.sha256 && echo "data/taxonomy/$$v.txt" && cat $$v.txt.sha256

# What CI's lint job runs (.github/workflows/ci.yml), minus actionlint.
lint:
	uv run ruff check .
	uv run mypy
	cd apps/web && pnpm lint && pnpm typecheck

test:
	uv run pytest -m "not integration"

# Service tests on real Postgres, OpenSearch and Floci containers (needs Docker).
test-int:
	uv run pytest -m integration

# End to end through the generated client; needs the API on :8020 with products indexed.
smoke:
	uv run python scripts/smoke.py

# The storefront (apps/web, Next.js) on :3020; the API must run on :8020.
web:
	cd apps/web && pnpm install && pnpm dev

web-test:
	cd apps/web && pnpm test && pnpm typecheck

# Slice 3's Done-when: a 2,000-product feed through the queues with failing model, OpenSearch and a killed worker.
# Starts its own API and workers on fresh queues; needs docker compose up and migrations, not Ollama.
chaos:
	uv run python -u scripts/chaos.py

OASDIFF := docker run --rm -v $(CURDIR):/specs:ro tufin/oasdiff:v1.35.0

# Regenerate everything derived from the contracts. Generated code is never edited by hand.
codegen:
	uv run python -c "from shelfsense_api.graphql import schema; print(schema.as_str())" > contracts/schema.graphql
	uv run python scripts/write_message_schemas.py
	uv run python scripts/write_money_fixtures.py
	cd apps/web && pnpm codegen
	uv run openapi-python-client generate --path contracts/openapi.yaml --output-path packages/clients/python \
		--meta uv --overwrite --config contracts/client-config.yaml

# Fails if the running code would break a client generated from contracts/openapi.yaml.
contract-check:
	@mkdir -p build
	uv run python -c "import json; from shelfsense_api.main import app; print(json.dumps(app.openapi(), indent=2))" > build/openapi.emitted.json
	$(OASDIFF) breaking --fail-on ERR /specs/contracts/openapi.yaml /specs/build/openapi.emitted.json

# Evals (evals/run.py). Replays recorded model replies; LIVE=1 calls Ollama and records them. Needs Postgres (the
# taxonomy embeddings) and OpenSearch; exits 1 when a gate is missed.
EVAL_FLAGS = $(if $(LIVE),--live) $(if $(BASELINE),--baseline evals/baseline.json)

golden:
	uv run python evals/golden/build.py

eval:
	uv run python -u evals/run.py --split dev $(EVAL_FLAGS)

eval-test:
	uv run python -u evals/run.py --split test $(EVAL_FLAGS)

# 1,000 searches through the API's search path on the catalog, by parse path (live; ~45 min with the reranker).
eval-latency:
	uv run python -u evals/run.py --split dev --only latency --live

# Enrichment and query models compared on the dev split (evals/SWEEP.md); LIVE=1 asks Ollama again.
sweep:
	uv run python -u evals/sweep.py $(if $(LIVE),--live)
