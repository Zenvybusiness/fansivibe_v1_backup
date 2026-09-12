// Public contract for the M9 Today's Look surface (#31–33, STEP 19.25).
//
// Other screens import only this contract — never `home/data/`
// internals. The backend look (title, occasion, components, reasons,
// scores, alternatives, selectedItemIds) is served verbatim; nothing here
// derives occasions, fabricates weather, logs wears, or writes signals.

export 'package:fansivibe/features/home/data/today_look_models.dart';
export 'package:fansivibe/features/home/data/today_look_repository.dart';
