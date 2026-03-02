PYTHON ?= python3
DOMAIN ?= agentic

.PHONY: help run scrape curate build intel serve demo clean

help:                       ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

run:                        ## Full pipeline (scrape → curate → build → intel)
	$(PYTHON) run.py --domain $(DOMAIN)

scrape:                     ## Only scrape sources
	$(PYTHON) run.py --domain $(DOMAIN) --scrape-only

curate:                     ## Only curate (score + filter cached data)
	$(PYTHON) run.py --domain $(DOMAIN) --curate-only

build:                      ## Only build site from cached scored data
	$(PYTHON) run.py --domain $(DOMAIN) --build-only

intel:                      ## Only generate intelligence reports
	$(PYTHON) run.py --domain $(DOMAIN) --intel-only

serve: build                ## Build and serve locally on port 8003
	cd output/site && $(PYTHON) -m http.server 8003

demo:                       ## Run with sample data (no network)
	$(PYTHON) run.py --domain $(DOMAIN) --demo

clean:                      ## Remove all generated data and output
	rm -rf data/raw/* data/scored.json data/reports/ output/site/*
