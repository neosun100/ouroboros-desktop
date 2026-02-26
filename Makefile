# Ouroboros — common development commands
# Usage: make test, make build, make build-release

.PHONY: test test-v health clean build build-release build-clean

# Run smoke tests (fast, no external deps needed at runtime)
test:
	python3 -m pytest tests/ -q --tb=short -k "not test_e2e_live"

# Run smoke tests with verbose output
test-v:
	python3 -m pytest tests/ -v --tb=long -k "not test_e2e_live"

# Run codebase health check (requires ouroboros importable)
health:
	python3 -c "from ouroboros.review import compute_complexity_metrics; \
		import pathlib, json; \
		m = compute_complexity_metrics(pathlib.Path('.')); \
		print(json.dumps(m, indent=2, default=str))"

# Build macOS .app + .dmg (development, no signing)
build:
	bash scripts/build_mac.sh

# Build macOS .app + .dmg (release, with signing + notarization)
build-release:
	bash scripts/build_mac.sh --sign

# Full clean (including python-standalone and build artifacts)
build-clean:
	bash scripts/build_mac.sh --clean

# Clean Python cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist
