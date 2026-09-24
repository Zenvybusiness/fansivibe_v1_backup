/// Public contract for the auth feature (D-AUTH-1).
///
/// Screens consume the repository + models through this barrel (the
/// today_look/discover precedent); the client's key helper travels
/// with it so callers mint one fresh key per register attempt.
library;

export 'data/auth_client.dart';
export 'data/auth_models.dart';
export 'data/auth_repository.dart';
export 'presentation/screens/create_account_screen.dart';
export 'presentation/screens/sign_in_screen.dart';
