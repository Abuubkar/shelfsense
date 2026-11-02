TAXONOMY_URL := https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt

.PHONY: taxonomy test test-int codegen contract-check smoke

# Download the official Google Product Taxonomy (with IDs) as data/taxonomy/<version>.txt plus its checksum.
# The version comes from the file's own header. Never fetched at runtime; scripts/load_taxonomy.py reads the file.
taxonomy:
	@mkdir -p data/taxonomy
	curl -fsSL $(TAXONOMY_URL) -o data/taxonomy/download.tmp
	@v=$$(head -1 data/taxonomy/download.tmp | tr -d '\r' | sed -n 's/^# Google_Product_Taxonomy_Version: //p'); \
	test -n "$$v" || { echo "no version header in the download"; exit 1; }; \
	mv data/taxonomy/download.tmp data/taxonomy/$$v.txt; \
	cd data/taxonomy && shasum -a 256 $$v.txt > $$v.txt.sha256 && echo "data/taxonomy/$$v.txt" && cat $$v.txt.sha256

test:
	uv run pytest -m "not integration"

# Service tests on real Postgres and OpenSearch containers (needs Docker).
test-int:
	uv run pytest -m integration

# End to end through the generated client; needs the API on :8020 with products indexed.
smoke:
	uv run python scripts/smoke.py

OASDIFF := docker run --rm -v $(CURDIR):/specs:ro tufin/oasdiff:v1.35.0

# Regenerate everything derived from the contracts. Generated code is never edited by hand.
codegen:
	uv run python -c "from shelfsense_api.graphql import schema; print(schema.as_str())" > contracts/schema.graphql
	uv run openapi-python-client generate --path contracts/openapi.yaml --output-path packages/clients/python \
		--meta uv --overwrite --config contracts/client-config.yaml

# Fails if the running code would break a client generated from contracts/openapi.yaml.
contract-check:
	@mkdir -p build
	uv run python -c "import json; from shelfsense_api.main import app; print(json.dumps(app.openapi(), indent=2))" > build/openapi.emitted.json
	$(OASDIFF) breaking --fail-on ERR /specs/contracts/openapi.yaml /specs/build/openapi.emitted.json
