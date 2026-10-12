/// Stage F0 mock virtual try-on — feature public contract.
///
/// Test data only: the mock provider renders a labelled SVG composite
/// (`is_mock: true` on every response). Nothing here calls a real AI
/// provider, and mock outputs must never enter saved-look, export, or
/// sharing flows as genuine try-on results.
library;

export 'data/try_on_client.dart';
export 'data/try_on_models.dart';
export 'data/try_on_repository.dart';
export 'presentation/try_on_screen.dart';
