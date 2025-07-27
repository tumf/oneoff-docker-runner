.PHONY: help install format lint test clean all bump-patch bump-minor bump-major bump-beta release

# Version management
VERSION_FILE := pyproject.toml

# Get current version (macOS compatible)
CURRENT_VERSION := $(shell grep -o '"[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*[^"]*"' $(VERSION_FILE) | tr -d '"')
VERSION_BASE := $(shell echo $(CURRENT_VERSION) | sed -E 's/([0-9]+\.[0-9]+\.[0-9]+).*/\1/')
VERSION_SUFFIX := $(shell echo $(CURRENT_VERSION) | grep -o -- "-[a-zA-Z0-9]\+" || echo "")
MAJOR := $(shell echo $(VERSION_BASE) | cut -d. -f1)
MINOR := $(shell echo $(VERSION_BASE) | cut -d. -f2)
PATCH := $(shell echo $(VERSION_BASE) | cut -d. -f3)
BETA_NUM := $(shell echo $(CURRENT_VERSION) | grep -o "beta[0-9]\+" | grep -o "[0-9]\+" || echo "0")

# Function to update version
define update_version
	@echo "Updating version to $(1)"
	@sed -i.bak 's/version = "[^"]*"/version = "$(1)"/' $(VERSION_FILE)
	@rm -f $(VERSION_FILE).bak
	@git add $(VERSION_FILE)
	@git commit -m "Bump version to $(1)"
	@git tag -a "v$(1)" -m "Version $(1)"
	@echo "Version updated to $(1). Don't forget to push with: git push && git push --tags"
endef

# Default target
help:
	@echo "Available targets:"
	@echo "  install     - Install dependencies"
	@echo "  format      - Format code with black and isort"
	@echo "  lint        - Run type checking with mypy"
	@echo "  test        - Run tests with pytest"
	@echo "  clean       - Clean up temporary files"
	@echo "  all         - Run format, lint, and test"
	@echo "  bump-patch  - Bump patch version (0.0.x)"
	@echo "  bump-minor  - Bump minor version (0.x.0)"
	@echo "  bump-major  - Bump major version (x.0.0)"
	@echo "  bump-beta   - Bump beta version (x.x.x-beta)"
	@echo "  release     - Remove beta suffix for release"

# Install dependencies
install:
	uv sync --dev

# Format code
format:
	uv run black .
	uv run isort .

# Type checking and linting
lint:
	@echo "Installing missing type stubs..."
	@uv add --dev types-docker types-requests || true
	uv run mypy . --install-types --non-interactive

# Run tests
test:
	@echo "Running tests with coverage..."
	uv run pytest -v --tb=short

# Clean up temporary files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

# Run all quality checks
all: format lint test

# Bump patch version (0.0.x)
bump-patch:
	$(eval NEW_PATCH := $(shell echo $$(($(PATCH) + 1))))
	$(eval NEW_VERSION := $(MAJOR).$(MINOR).$(NEW_PATCH))
	$(call update_version,$(NEW_VERSION))

# Bump minor version (0.x.0)
bump-minor:
	$(eval NEW_MINOR := $(shell echo $$(($(MINOR) + 1))))
	$(eval NEW_VERSION := $(MAJOR).$(NEW_MINOR).0)
	$(call update_version,$(NEW_VERSION))

# Bump major version (x.0.0)
bump-major:
	$(eval NEW_MAJOR := $(shell echo $$(($(MAJOR) + 1))))
	$(eval NEW_VERSION := $(NEW_MAJOR).0.0)
	$(call update_version,$(NEW_VERSION))

# Bump beta version (x.x.x-beta)
bump-beta:
	@if echo "$(CURRENT_VERSION)" | grep -q "beta"; then \
		NEW_BETA_NUM=$$(($(BETA_NUM) + 1)); \
		NEW_VERSION="$(VERSION_BASE)-beta$$NEW_BETA_NUM"; \
	else \
		NEW_PATCH=$$(($(PATCH) + 1)); \
		NEW_VERSION="$(MAJOR).$(MINOR).$$NEW_PATCH-beta1"; \
	fi; \
	echo "Updating version to $$NEW_VERSION"; \
	sed -i.bak 's/version = "[^"]*"/version = "'"$$NEW_VERSION"'"/' $(VERSION_FILE); \
	rm -f $(VERSION_FILE).bak; \
	git add $(VERSION_FILE); \
	git commit -m "Bump version to $$NEW_VERSION"; \
	git tag -a "v$$NEW_VERSION" -m "Version $$NEW_VERSION"; \
	echo "Version updated to $$NEW_VERSION. Don't forget to push with: git push && git push --tags"

# Remove beta suffix for release (x.x.x-betaX -> x.x.x)
release:
	$(eval NEW_VERSION := $(VERSION_BASE))
	$(call update_version,$(NEW_VERSION))