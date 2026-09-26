# via/amk docs: section headers generated in place, and GitHub-faithful local previews of the pages.

# Self-contained: both tools are stdlib scripts under docs/tools that uv runs; a page with no header markers is left as it is.
docs.pages   ?= README.md $(wildcard docs/*.md)
docs.img     ?= docs/img/hdr
docs.repo    ?= Robot-Wranglers/ape-make
docs.port    ?= 6419
mdheaders     = uv run --quiet --script docs/tools/mdheaders.py --img $(docs.img)

.PHONY: docs.headers docs.check docs.test docs.serve

docs.headers:
	@# Regenerate every header block in docs.pages, and its images under docs.img.
	$(mdheaders) $(docs.pages)

docs.check:
	@# Fail when a header block or image is out of date; writes nothing.
	$(mdheaders) --check $(docs.pages) \
	  || { echo "docs.check: a header is out of date -- run make docs.headers" >&2; exit 1; }

docs.test:
	@# The header tool's own tests, in a throwaway environment with pytest.
	uv run --quiet --with pytest pytest -q -p no:cacheprovider docs/tools

docs.serve:
	@# Serve every page as github.com renders it, at http://localhost:$(docs.port)/; reload after an edit, add ?theme=dark or ?theme=light to pin one.
	command -v gh >/dev/null || { echo "docs.serve: gh is not on PATH -- the preview renders through gh api" >&2; exit 1; }
	echo "docs.serve: serving at http://localhost:$(docs.port)/" >&2
	uv run --quiet --script docs/tools/preview.py $(docs.repo) $(docs.port)
