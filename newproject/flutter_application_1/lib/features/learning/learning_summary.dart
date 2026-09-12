// Public contract for the M10 learning summary read (#34, STEP 19.16).
//
// Other features must import only this contract — never `learning/data/`
// internals. The backend summary (score, breakdown, streak, recent
// signals) is served verbatim; nothing here computes or caches it.

export 'package:fansivibe/features/learning/data/learning_summary_models.dart';
export 'package:fansivibe/features/learning/data/learning_summary_repository.dart';
