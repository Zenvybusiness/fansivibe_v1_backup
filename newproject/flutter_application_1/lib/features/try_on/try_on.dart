/// Virtual Try-On feature public contract.
///
/// Integrates with `/v1/tryon/*` endpoints via [TryOnRepository] and renders
/// mock test previews (`is_mock: true`) or genuine AI try-on results (`is_mock: false`)
/// with strict privacy, consent, and AI-disclosure guarantees.
library;

export 'data/try_on_client.dart';
export 'data/try_on_device_saver.dart';
export 'data/try_on_models.dart';
export 'data/try_on_repository.dart';
export 'presentation/try_on_screen.dart';
