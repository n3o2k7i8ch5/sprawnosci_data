# sprawnosci_data

Sprawności (scout proficiency badges) data, Isar models and import scripts for HarcApp.

This package was extracted from `harcapp_core` to keep the data layer separate from UI widgets. Widgets and screens continue to live in `harcapp/` and `harcapp_web/`.

## Contents

- `assets/sprawnosci/` — source data: YAML files + SVG icons per book
- `assets/sprawnosci_db.isar.tar` — compiled Isar database (tar archive)
- `lib/src/models.dart` — Isar data models (`SprawBook`, `SprawGroup`, `SprawFamily`, `Spraw`, `SprawTask`, `SprawExternal`)
- `lib/src/data_importer.dart` — filesystem → Isar importer
- `lib/src/all_spraw_book_slugs.dart` — `SprawBookSlug` enum mapping book slugs to colors/icons/org
- `lib/src/open_isar.dart` / `lib/src/isar_utils.dart` — runtime DB initialization for apps
- `bin/generate_db.dart` — CLI to regenerate `sprawnosci_db.isar.tar` from YAMLs
- `bin/generate_assets_list.dart` — CLI to update the asset list in `pubspec.yaml`
- `tools/sprawnosci_converter.py` — Python tool that converts legacy Dart book data to YAML

## Public API

Import the barrel:

```dart
import 'package:sprawnosci_data/sprawnosci_data.dart';
```

## Common tasks

```bash
make install              # flutter pub get
make generate             # regenerate Isar adapters after editing models
make import_spraw_books   # rebuild assets/sprawnosci_db.isar.tar from YAMLs
make generate_assets      # update the asset list in pubspec.yaml
```

For the data structure and conventions, see the original notes preserved from `harcapp_core/lib/sprawnosci/README.md` (also reproduced as `DATA.md`).
