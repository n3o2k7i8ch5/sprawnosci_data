.PHONY: install
install:
	@flutter pub get
	@cp scripts/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Git hook installed."

# Regenerate Isar adapters (after editing lib/src/models.dart)
.PHONY: generate
generate:
	@flutter pub get
	dart run build_runner build --delete-conflicting-outputs

# Defaults (can be overridden on the make command line)
ISAR_DIR?=assets/sprawnosci_db.isar

# Import all sprawnosci books from assets/sprawnosci, output as .tar
.PHONY: import_spraw_books
import_spraw_books:
	@echo "Importing all sprawnosci books -> Isar dir: $(ISAR_DIR)"
	dart run bin/generate_db.dart --tar "$(ISAR_DIR)"

# Regenerate the asset directory list and update pubspec.yaml in place.
.PHONY: generate_assets
generate_assets:
	dart run bin/generate_assets_list.dart --update-pubspec
