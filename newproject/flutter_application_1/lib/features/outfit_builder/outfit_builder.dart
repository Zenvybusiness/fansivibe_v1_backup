// Public contract for the M13 outfit builder surface (#41–42, PHASE 2).
//
// Screens import only this contract — never `outfit_builder/data/`
// internals. The backend outfit (title, score, components, reasons,
// metrics, echoes) is served verbatim; nothing here derives outfits,
// fabricates weather, logs wears, or writes signals.

export 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
export 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
