// Public contract for the M11 feedback surface (#35, PHASE 2).
//
// Screens in any feature import only this contract — never
// `feedback/data/` internals. Reactions are served by the backend
// verbatim; nothing here records signals, marks styled days, logs
// wears, or fabricates acks.

export 'package:fansivibe/features/feedback/data/feedback_models.dart';
export 'package:fansivibe/features/feedback/data/feedback_repository.dart';
