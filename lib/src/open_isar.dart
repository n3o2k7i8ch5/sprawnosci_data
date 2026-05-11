import 'package:isar_community/isar.dart';

import 'models.dart';

Future<Isar> openIsar(String dbDir) => Isar.open(
  [SprawBookSchema, SprawGroupSchema, SprawFamilySchema, SprawSchema, SprawTaskSchema, SprawExternalSchema],
  directory: dbDir,
);