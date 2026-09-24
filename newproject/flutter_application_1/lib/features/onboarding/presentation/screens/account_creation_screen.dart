import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

class AccountCreationScreen extends StatefulWidget {
  /// Auth source (D-AUTH-1). Defaults to the live repository; tests
  /// inject a fake. [mode] is 'register' or 'login' (via route extra).
  const AccountCreationScreen({super.key, this.authRepository, this.mode = 'register'});

  final AuthRepository? authRepository;
  final String mode;

  @override
  State<AccountCreationScreen> createState() => _AccountCreationScreenState();
}

class _AccountCreationScreenState extends State<AccountCreationScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _avatarAnim;
  late Animation<double> _formAnim;
  late Animation<double> _ctaAnim;

  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _nameController = TextEditingController();
  bool _isValid = false;
  bool _submitting = false;
  String? _authError;
  late final AuthRepository _auth;

  bool get _isLogin => widget.mode == 'login';

  static const _paletteColors = [
    Color(0xFF2D2D2D),
    Color(0xFF8B7D6B),
    Color(0xFFC5A059),
    Color(0xFFF5F0EB),
    Color(0xFF4A6741),
  ];

  @override
  void initState() {
    super.initState();
    _auth = widget.authRepository ?? AuthRepositoryImpl();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
    _avatarAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.0, 0.3, curve: Curves.easeOut),
      ),
    );
    _formAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.2, 0.6, curve: Curves.easeOut),
      ),
    );
    _ctaAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.4, 0.8, curve: Curves.easeOut),
      ),
    );
    _controller.forward();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    _controller.dispose();
    super.dispose();
  }

  /// Submits register (create mode) or login (sign-in mode) against
  /// the real backend (D-AUTH-1). Success persists the session inside
  /// the client and navigates home; failures render truthful copy —
  /// never a fake login success.
  Future<void> _onSubmit() async {
    if (_submitting) return;
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    if (email.isEmpty || password.isEmpty) {
      setState(() {
        _authError = 'Enter your email and password to continue.';
      });
      return;
    }
    setState(() {
      _submitting = true;
      _authError = null;
    });
    final AuthResult result;
    if (_isLogin) {
      result = await _auth.login(email: email, password: password);
    } else {
      result = await _auth.register(
        email: email,
        password: password,
        displayName: _nameController.text.trim().isNotEmpty
            ? _nameController.text.trim()
            : null,
        idempotencyKey: newAuthIdempotencyKey(),
      );
    }
    if (!mounted) return;
    setState(() => _submitting = false);
    if (result.isAuthenticated) {
      final name = result.displayName ??
          (_nameController.text.isNotEmpty ? _nameController.text : null);
      if (name != null) {
        LocalStorage.displayName = name;
      }
      if (_isLogin) {
        // Returning user logging in: enters established home
        UserSession.isReturningUser = true;
        UserSession.hasSavedWardrobeItem = true;
        context.goNamed(
          RouteNames.home,
          extra: {
            'display_name': name,
            'is_login': true,
          },
        );
      } else {
        // New user registering: enters first-time home
        LocalStorage.onboardingComplete = true;
        context.goNamed(
          RouteNames.home,
          extra: {
            'onboarding_complete': true,
            'display_name': name,
          },
        );
      }
      return;
    }
    setState(() {
      _authError = switch (result.status) {
        AuthStatus.invalidCredentials =>
          'Those credentials didn\'t match. Check your email and password and try again.',
        AuthStatus.emailTaken =>
          'That email is already registered. Try signing in instead.',
        AuthStatus.invalidInput =>
          'Check your email and password — they don\'t look quite right.',
        AuthStatus.providerUnavailable =>
          'Social sign-in isn\'t available yet. Use email instead.',
        AuthStatus.rateLimited =>
          'Too many attempts. Wait a moment and try again.',
        AuthStatus.networkError =>
          'Couldn\'t reach the sign-in service. Check your connection and try again.',
        AuthStatus.authenticated || AuthStatus.signedOut => null,
      };
    });
  }

  void _onCreateAccount() => _onSubmit();

  Future<void> _onSocialSignIn(String provider) async {
    if (_submitting) return;
    setState(() {
      _submitting = true;
      _authError = null;
    });
    // No external identity provider is configured (honest 502 behind
    // this call): the result is always providerUnavailable and no
    // session is ever fabricated from an unverified token.
    final result = await _auth.socialSignIn(
      provider: provider,
      providerToken: '',
    );
    if (!mounted) return;
    setState(() {
      _submitting = false;
      // No identity provider is configured, so every social attempt fails:
      // always say so instead of clearing the error silently.
      _authError = result.isAuthenticated
          ? null
          : 'Social sign-in isn\'t available yet. Use email instead.';
    });
  }

  void _onMaybeLater() {
    context.goNamed(
      RouteNames.home,
      extra: {'onboarding_complete': true, 'saved_locally': true, 'analysis_cached': true},
    );
  }

  void _validate() {
    final email = _emailController.text;
    setState(() {
      _isValid = email.contains('@') && email.contains('.') && email.length > 5;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 24.0;
            final contentMaxWidth = maxWidth > 600 ? 420.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                    ),
                    child: Column(
                      children: [
                        SizedBox(height: FansivibeSpacing.xxl + 16),
                        _buildAvatarSection(),
                        SizedBox(height: FansivibeSpacing.xl),
                        _buildFormSection(),
                        SizedBox(height: FansivibeSpacing.lg),
                        _buildCtaSection(),
                        SizedBox(height: FansivibeSpacing.lg),
                        _buildSocialSection(),
                SizedBox(height: FansivibeSpacing.md),
                FansiButton.tertiary(
                  label: _isLogin ? 'Sign In' : 'Create Account',
                  onPressed:
                      (_isValid && !_submitting) ? _onCreateAccount : null,
                ),
                        SizedBox(height: FansivibeSpacing.xxl),
                        FansiButton.tertiary(
                          label: 'Maybe Later — Save Locally',
                          onPressed: _onMaybeLater,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildAvatarSection() {
    return AnimatedBuilder(
      animation: _avatarAnim,
      builder: (context, _) {
        return Opacity(
          opacity: _avatarAnim.value,
          child: Transform.translate(
            offset: Offset(0, 30 * (1 - _avatarAnim.value)),
            child: Column(
              children: [
                Container(
                  width: 88,
                  height: 88,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: SweepGradient(
                      colors: _paletteColors.map((c) => c).toList(),
                    ),
                    border: Border.all(
                      color: FansivibeColors.primary.withValues(alpha: 0.3),
                      width: 2,
                    ),
                  ),
                  child: Center(
                    child: Container(
                      width: 78,
                      height: 78,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: FansivibeColors.surface,
                      ),
                      child: Icon(
                        Icons.person_outline_rounded,
                        size: 40,
                        color: FansivibeColors.primary.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                ),
                SizedBox(height: FansivibeSpacing.lg),
                Text(
                  _isLogin ? 'Welcome Back' : 'Save Your Style Journey',
                  textAlign: TextAlign.center,
                  style: FansivibeTypography.headlineMediumWithFamily.copyWith(
                    fontSize: 24,
                    height: 1.2,
                  ),
                ),
                SizedBox(height: FansivibeSpacing.sm),
                Text(
                  _isLogin
                      ? 'Sign in to pick up your style where you left off.'
                      : 'Your Style DNA, score, and analysis\nwill be saved to your account.',
                  textAlign: TextAlign.center,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFormSection() {
    return AnimatedBuilder(
      animation: _formAnim,
      builder: (context, _) {
        return Opacity(
          opacity: _formAnim.value,
          child: Transform.translate(
            offset: Offset(0, 20 * (1 - _formAnim.value)),
            child: Column(
              children: [
                TextField(
                  controller: _emailController,
                  onChanged: (_) => _validate(),
                  keyboardType: TextInputType.emailAddress,
                  autocorrect: false,
                  style: FansivibeTypography.bodyLargeWithFamily,
                  decoration: InputDecoration(
                    hintText: 'Email address',
                    filled: true,
                    fillColor: FansivibeColors.surfaceContainerLow.withValues(
                      alpha: 0.5,
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide.none,
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide.none,
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide(
                        color: FansivibeColors.primary,
                        width: 1.5,
                      ),
                    ),
                  ),
                ),
                SizedBox(height: FansivibeSpacing.md),
                TextField(
                  controller: _passwordController,
                  obscureText: true,
                  style: FansivibeTypography.bodyLargeWithFamily,
                  decoration: InputDecoration(
                    hintText: 'Password',
                    filled: true,
                    fillColor: FansivibeColors.surfaceContainerLow.withValues(
                      alpha: 0.5,
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide.none,
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide.none,
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide(
                        color: FansivibeColors.primary,
                        width: 1.5,
                      ),
                    ),
                  ),
                ),
                SizedBox(height: FansivibeSpacing.md),
                TextField(
                  controller: _nameController,
                  style: FansivibeTypography.bodyLargeWithFamily,
                  decoration: InputDecoration(
                    hintText: 'Your name (optional)',
                    filled: true,
                    fillColor: FansivibeColors.surfaceContainerLow.withValues(
                      alpha: 0.5,
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide.none,
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide.none,
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: FansivibeRadius.smBorder,
                      borderSide: BorderSide(
                        color: FansivibeColors.primary,
                        width: 1.5,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildCtaSection() {
    return AnimatedBuilder(
      animation: _ctaAnim,
      builder: (context, _) {
        return Opacity(
          opacity: _ctaAnim.value,
          child: Column(
            children: [
              if (_authError != null)
                Padding(
                  padding: EdgeInsets.only(bottom: FansivibeSpacing.md),
                  child: Text(
                    _authError!,
                    textAlign: TextAlign.center,
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.error,
                      height: 1.4,
                    ),
                  ),
                ),
              FansiButton.primary(
                label: _submitting
                    ? 'Please wait…'
                    : (_isLogin ? 'Sign In' : 'Create Account'),
                icon: Icons.arrow_forward_rounded,
                onPressed:
                    (_isValid && !_submitting) ? _onCreateAccount : null,
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildSocialSection() {
    return AnimatedBuilder(
      animation: _ctaAnim,
      builder: (context, _) {
        return Opacity(
          opacity: _ctaAnim.value,
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Divider(
                      color: FansivibeColors.outlineVariant.withValues(
                        alpha: 0.3,
                      ),
                    ),
                  ),
                  Flexible(
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: FansivibeSpacing.md,
                      ),
                      child: Text(
                        'or continue with',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: FansivibeTypography.labelSmallWithFamily
                            .copyWith(
                              color: FansivibeColors.secondary.withValues(
                                alpha: 0.5,
                              ),
                            ),
                      ),
                    ),
                  ),
                  Expanded(
                    child: Divider(
                      color: FansivibeColors.outlineVariant.withValues(
                        alpha: 0.3,
                      ),
                    ),
                  ),
                ],
              ),
              SizedBox(height: FansivibeSpacing.md),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: () => _onSocialSignIn('google'),
                      icon: const Icon(Icons.g_mobiledata_rounded, size: 22),
                      label: Text(
                        'Google',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      style: FilledButton.styleFrom(
                        backgroundColor: FansivibeColors.surfaceContainerHigh,
                        foregroundColor: FansivibeColors.onSurface,
                        shape: RoundedRectangleBorder(
                          borderRadius: FansivibeRadius.smBorder,
                        ),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 14,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: FansivibeSpacing.sm + 4),
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: () => _onSocialSignIn('apple'),
                      icon: const Icon(Icons.apple, size: 22),
                      label: Text(
                        'Apple',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      style: FilledButton.styleFrom(
                        backgroundColor: FansivibeColors.surfaceContainerHigh,
                        foregroundColor: FansivibeColors.onSurface,
                        shape: RoundedRectangleBorder(
                          borderRadius: FansivibeRadius.smBorder,
                        ),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 14,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}
