// Public contract for the M14 Discover surface (#43–44, UC-31).
//
// Other screens import only this contract — never `discover/data/`
// internals. The backend look feed (ranked catalog codes with verbatim
// titles, descriptions, scores, and reasons) is served as-is; nothing
// here derives scores, reorders the feed, fabricates tags/ensembles,
// logs wears, or writes signals.

export 'package:fansivibe/features/discover/data/discover_models.dart';
export 'package:fansivibe/features/discover/data/discover_repository.dart';
