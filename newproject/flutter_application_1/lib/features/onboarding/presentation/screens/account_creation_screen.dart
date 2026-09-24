import 'package:flutter/material.dart';
import 'package:fansivibe/features/auth/auth.dart';

/// Legacy adapter for the account creation screen.
///
/// Delegates to [SignInScreen] when [mode] == 'login', or [CreateAccountScreen]
/// when [mode] == 'register', maintaining 100% backward compatibility for existing
/// route references and tests while runtime routes use dedicated [CreateAccountScreen]
/// and [SignInScreen].
class AccountCreationScreen extends StatelessWidget {
  const AccountCreationScreen({
    super.key,
    this.authRepository,
    this.mode = 'register',
  });

  final AuthRepository? authRepository;
  final String mode;

  @override
  Widget build(BuildContext context) {
    if (mode == 'login') {
      return SignInScreen(
        authRepository: authRepository,
        initialShowEmailForm: true,
      );
    }
    return CreateAccountScreen(
      authRepository: authRepository,
      initialShowEmailForm: true,
    );
  }
}
