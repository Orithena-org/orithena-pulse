# Orithena Pulse - Makefile
# GitHub Pages shell. Pipeline lives in orithena-org/content/

PYTHON ?= python3
DOMAIN ?= pulse
ORG_DIR = ../orithena-org

.PHONY: help run scrape build demo clean serve

help:                       ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

run:                        ## Full pipeline (scrape + curate + build + post)
	cd $(ORG_DIR) && $(PYTHON) -m content.pipeline --domain $(DOMAIN)

scrape:                     ## Only scrape sources
	cd $(ORG_DIR) && $(PYTHON) -m content.pipeline --domain $(DOMAIN) --scrape-only

build:                      ## Only build site from cached data
	cd $(ORG_DIR) && $(PYTHON) -m content.pipeline --domain $(DOMAIN) --build-only

demo:                       ## Run with sample data (no network)
	cd $(ORG_DIR) && $(PYTHON) -m content.pipeline --domain $(DOMAIN) --demo --no-post

serve: build                ## Build and serve locally on port 8003
	cd output/site && $(PYTHON) -m http.server 8003

clean:                      ## Remove all generated data and output
	rm -rf data/raw/* data/scored.json data/reports/ output/site/*
