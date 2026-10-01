# via/amk docs: GitHub-faithful local previews of the markdown, and the generated README header art.

# Pages render through GitHub's markdown api by way of gh, styled by github-markdown-css; uv runs the stdlib scripts.
docs.repo    ?= Robot-Wranglers/ape-make
docs.port    ?= 6419
docs.spec    := docs/headers.toml
docs.img     := docs/img/hdr
docs.lab     := docs/lab.md

.PHONY: docs.headers docs.serve docs.lab

docs.headers:
	@# Regenerate the header svgs and the lab page from the spec.
	$(call log, docs, header art from $(docs.spec) into $(docs.img) and $(docs.lab))
	uv run --quiet --script docs/tools/headers.py $(docs.spec) $(docs.img) $(docs.lab)

docs.serve:
	@# Serve every page as github.com renders it, at http://localhost:$(docs.port)/; reload after an edit, add ?theme=dark or ?theme=light to pin one.
	command -v gh >/dev/null || $(call die, docs, gh is not on PATH -- the preview renders through gh api)
	$(call log, docs, serving at http://localhost:$(docs.port)/ -- $(docs.lab) is the header lab)
	uv run --quiet --script docs/tools/preview.py $(docs.repo) $(docs.port)

docs.lab: docs.headers docs.serve
	@# Regenerate the header art, then serve.
