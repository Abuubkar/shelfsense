TAXONOMY_URL := https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt

.PHONY: taxonomy test

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
	uv run pytest
