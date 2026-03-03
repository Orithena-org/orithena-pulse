# Orithena Organization Vision

## What Orithena Is

Orithena is an AI-run organization that builds products generating revenue for human flourishing. An autonomous AI agent (Scout) handles development, research, and operations, with human oversight on strategy and approvals. Everything runs on free-tier infrastructure with no persistent servers.

## Current Products

**Madison Events** — Local events aggregator for Madison, WI. Scrapes event sources, generates a static site, publishes a newsletter via beehiiv, and creates social media content. Goal: become the go-to local events resource and generate newsletter ad revenue.

**Orithena Pulse** — Content intelligence pipeline. Scrapes Hacker News, arXiv, GitHub trending, and RSS feeds daily. Scores and curates items by relevance to our work. Publishes a daily digest static site and structured intelligence reports. Goal: surface actionable signals for what to build or improve.

## Tech Stack

- **Language:** Python
- **CI/CD:** GitHub Actions
- **Hosting:** GitHub Pages (static sites)
- **Site generation:** Jinja2 templates → static HTML
- **Newsletter:** beehiiv (Madison Events)
- **LLM:** Claude API for content analysis, generation, and agent tasks
- **Orchestration:** Docker containers, filesystem IPC, no persistent servers

## What We Would Ship

- Scraper improvements (new sources, better parsing, error handling)
- Data quality enhancements (deduplication, scoring accuracy)
- New content sources for either product
- Newsletter and email features (formatting, scheduling, segmentation)
- SEO improvements (meta tags, structured data, sitemaps)
- Analytics integration (lightweight, privacy-respecting)
- Site UX improvements (navigation, readability, mobile)
- Automation capabilities (scheduled tasks, GitHub Actions workflows)
- LLM-powered features (summarization, categorization, content generation)
- Social content generation and publishing

## What We Would NOT Ship

- Anything requiring persistent servers or paid hosting
- Paid infrastructure beyond free tiers (databases, compute, storage)
- Heavy ML model training or fine-tuning
- Features unrelated to Madison Events or Orithena Pulse
- Complex frontend frameworks (React, Next.js) — we use static HTML
- Services requiring ongoing manual maintenance

## Evaluation Criteria for New Ideas

When evaluating whether something is worth building:
1. Does it directly improve Madison Events or Orithena Pulse?
2. Can it run on free-tier infrastructure (GitHub Actions, GitHub Pages)?
3. Can it be implemented in Python with minimal new dependencies?
4. Does it move us toward revenue (newsletter growth, content quality, audience)?
5. Can an AI agent implement and maintain it autonomously?
