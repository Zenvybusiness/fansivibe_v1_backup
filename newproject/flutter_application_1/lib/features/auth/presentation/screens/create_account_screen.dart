import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Screen A: New User / Create Account Screen.
///
/// Specifically designed for users who do not already have a Fansivibe account.
/// Communicates "Create your account" and "Start your personal style journey".
/// Provides Continue with Google, Continue with Apple, and Continue with Email.
/// Email flow supports Email, Password, Confirm Password, optional Name, and
/// Create Account.
/// Bottom navigation links directly to the Existing User / Sign In screen.
class CreateAccountScreen extends StatefulWidget {
  const CreateAccountScreen({
    super.key,
    this.authRepository,
    this.initialShowEmailForm = false,
  });

  final AuthRepository? authRepository;
  final bool initialShowEmailForm;

  @override
  State<CreateAccountScreen> createState() => _CreateAccountScreenState();
}

class _CreateAccountScreenState extends State<CreateAccountScreen>
    with SingleTickerProviderStateMixin {
  late final AuthRepository _auth;
  late AnimationController _animController;
  late Animation<double> _fadeAnim;

  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _nameController = TextEditingController();

  bool _showEmailForm = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _submitting = false;
  String? _authError;
  bool _emailTaken = false;

  @override
  void initState() {
    super.initState();
    _auth = widget.authRepository ?? AuthRepositoryImpl();
    _showEmailForm = widget.initialShowEmailForm;
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    _fadeAnim = CurvedAnimation(
      parent: _animController,
      curve: Curves.easeOut,
    );
    _animController.forward();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _nameController.dispose();
    _animController.dispose();
    super.dispose();
  }

  void _onToggleEmailForm() {
    setState(() {
      _showEmailForm = !_showEmailForm;
      _authError = null;
      _emailTaken = false;
    });
  }

  Future<void> _onSocialSignIn(String provider) async {
    if (_submitting) return;
    setState(() {
      _submitting = true;
      _authError = null;
      _emailTaken = false;
    });

    final result = await _auth.socialSignIn(
      provider: provider,
      providerToken: '',
    );
    if (!mounted) return;
    setState(() => _submitting = false);

    if (result.isAuthenticated) {
      _handleAuthSuccess(result.displayName);
      return;
    }

    setState(() {
      _authError = switch (result.status) {
        AuthStatus.providerUnavailable =>
          'Social sign-in isn\'t available yet. Use email instead.',
        AuthStatus.rateLimited =>
          'Too many attempts. Wait a moment and try again.',
        AuthStatus.networkError =>
          'Couldn\'t reach the sign-in service. Check your connection and try again.',
        _ => 'Social sign-in was not completed. Try again or use email.',
      };
    });
  }

  Future<void> _onCreateAccountWithEmail() async {
    if (_submitting) return;

    final email = _emailController.text.trim();
    final password = _passwordController.text;
    final confirmPassword = _confirmPasswordController.text;

    if (email.isEmpty || password.isEmpty) {
      setState(() {
        _authError = 'Enter your email and password to create your account.';
        _emailTaken = false;
      });
      return;
    }

    if (!email.contains('@') || !email.contains('.') || email.length < 5) {
      setState(() {
        _authError = 'Please enter a valid email address.';
        _emailTaken = false;
      });
      return;
    }

    if (password.length < 6) {
      setState(() {
        _authError = 'Password must be at least 6 characters.';
        _emailTaken = false;
      });
      return;
    }

    if (confirmPassword.isNotEmpty && password != confirmPassword) {
      setState(() {
        _authError = 'Passwords do not match.';
        _emailTaken = false;
      });
      return;
    }

    setState(() {
      _submitting = true;
      _authError = null;
      _emailTaken = false;
    });

    final displayName = _nameController.text.trim().isNotEmpty
        ? _nameController.text.trim()
        : null;

    final result = await _auth.register(
      email: email,
      password: password,
      displayName: displayName,
      idempotencyKey: newAuthIdempotencyKey(),
    );

    if (!mounted) return;
    setState(() => _submitting = false);

    if (result.isAuthenticated) {
      _handleAuthSuccess(result.displayName ?? displayName);
      return;
    }

    setState(() {
      _emailTaken = result.status == AuthStatus.emailTaken;
      _authError = switch (result.status) {
        AuthStatus.emailTaken =>
          'An account with this email already exists. Sign In instead.',
        AuthStatus.invalidInput =>
          'Check your email and password — they don\'t look quite right.',
        AuthStatus.rateLimited =>
          'Too many attempts. Wait a moment and try again.',
        AuthStatus.networkError =>
          'Couldn\'t reach the sign-in service. Check your connection and try again.',
        _ => 'Could not create your account. Please try again.',
      };
    });
  }

  void _handleAuthSuccess(String? name) {
    if (name != null && name.isNotEmpty) {
      LocalStorage.displayName = name;
    }
    // New user registration leads to onboarding completion and first-time home
    LocalStorage.onboardingComplete = true;
    context.goNamed(
      RouteNames.home,
      extra: {
        'onboarding_complete': true,
        'display_name': name,
      },
    );
  }

  void _onNavigateToSignIn() {
    // Avoid piling up infinite auth navigation stack
    if (Navigator.of(context).canPop()) {
      context.pushReplacementNamed(RouteNames.signIn);
    } else {
      context.goNamed(RouteNames.signIn);
    }
  }

  void _onMaybeLater() {
    context.goNamed(
      RouteNames.home,
      extra: {
        'onboarding_complete': true,
        'saved_locally': true,
        'analysis_cached': true,
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: Navigator.of(context).canPop()
            ? IconButton(
                icon: const Icon(
                  Icons.arrow_back_ios_new_rounded,
                  color: FansivibeColors.onSurface,
                  size: 20,
                ),
                onPressed: () => Navigator.of(context).maybePop(),
                tooltip: 'Back',
              )
            : null,
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 24.0;
            final contentMaxWidth = maxWidth > 600 ? 440.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
                    child: FadeTransition(
                      opacity: _fadeAnim,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          const SizedBox(height: 12),
                          _buildBrandHeader(),
                          const SizedBox(height: 28),
                          _buildTitleSection(),
                          const SizedBox(height: 32),
                          if (_authError != null) _buildErrorMessage(),
                          _buildPrimaryAuthOptions(),
                          if (_showEmailForm) ...[
                            const SizedBox(height: 24),
                            _buildEmailRegistrationForm(),
                          ],
                          const SizedBox(height: 36),
                          _buildSignInSwitchFooter(),
                          const SizedBox(height: 24),
                          _buildGuestTertiaryOption(),
                          const SizedBox(height: 20),
                        ],
                      ),
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

  Widget _buildBrandHeader() {
    return Column(
      children: [
        Text(
          'F A N S I V I B E',
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            color: FansivibeColors.onSurface,
            fontSize: 20,
            letterSpacing: 6,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'APPEARANCE INTELLIGENCE',
          style: FansivibeTypography.labelSmallWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 3,
            fontWeight: FontWeight.w500,
            fontSize: 10,
          ),
        ),
      ],
    );
  }

  Widget _buildTitleSection() {
    return Column(
      children: [
        Text(
          'Create your account',
          textAlign: TextAlign.center,
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            color: FansivibeColors.onSurface,
            fontSize: 30,
            fontWeight: FontWeight.w500,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Start your personal style journey',
          textAlign: TextAlign.center,
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            fontSize: 15,
            height: 1.4,
          ),
        ),
      ],
    );
  }

  Widget _buildErrorMessage() {
    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.smdBorder,
        border: Border.all(
          color: _emailTaken
              ? FansivibeColors.primary.withValues(alpha: 0.6)
              : FansivibeColors.error.withValues(alpha: 0.6),
          width: 1.2,
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Icon(
                _emailTaken ? Icons.info_outline_rounded : Icons.error_outline_rounded,
                color: _emailTaken ? FansivibeColors.primary : FansivibeColors.error,
                size: 20,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  _authError!,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: _emailTaken
                        ? FansivibeColors.onSurface
                        : FansivibeColors.error,
                    fontSize: 13,
                    height: 1.3,
                  ),
                ),
              ),
            ],
          ),
          if (_emailTaken) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _onNavigateToSignIn,
                style: TextButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(
                  'Go to Sign In →',
                  style: TextStyle(
                    color: FansivibeColors.primary,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildPrimaryAuthOptions() {
    return Column(
      children: [
        _SocialAuthButton(
          label: 'Continue with Google',
          icon: _buildGoogleIcon(),
          onPressed: _submitting ? null : () => _onSocialSignIn('google'),
        ),
        const SizedBox(height: 14),
        _SocialAuthButton(
          label: 'Continue with Apple',
          icon: const Icon(Icons.apple, size: 22, color: FansivibeColors.onSurface),
          onPressed: _submitting ? null : () => _onSocialSignIn('apple'),
        ),
        const SizedBox(height: 14),
        _SocialAuthButton(
          label: 'Continue with Email',
          icon: const Icon(
            Icons.mail_outline_rounded,
            size: 20,
            color: FansivibeColors.onSurface,
          ),
          onPressed: _onToggleEmailForm,
          isHighlighted: _showEmailForm,
          trailing: Icon(
            _showEmailForm ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
            color: FansivibeColors.secondary,
            size: 20,
          ),
        ),
      ],
    );
  }

  Widget _buildGoogleIcon() {
    return Container(
      width: 20,
      height: 20,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: FansivibeColors.onSurface.withValues(alpha: 0.5), width: 1.2),
      ),
      child: const Text(
        'G',
        style: TextStyle(
          color: FansivibeColors.onSurface,
          fontWeight: FontWeight.w700,
          fontSize: 12,
          fontFamily: 'Inter',
        ),
      ),
    );
  }

  Widget _buildEmailRegistrationForm() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.35),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Create account with Email',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _emailController,
            keyboardType: TextInputType.emailAddress,
            autocorrect: false,
            style: FansivibeTypography.bodyLargeWithFamily,
            decoration: _inputDecoration(
              hint: 'Email address',
              icon: Icons.alternate_email_rounded,
            ),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _passwordController,
            obscureText: _obscurePassword,
            style: FansivibeTypography.bodyLargeWithFamily,
            decoration: _inputDecoration(
              hint: 'Password',
              icon: Icons.lock_outline_rounded,
              suffixIcon: IconButton(
                icon: Icon(
                  _obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                  size: 20,
                  color: FansivibeColors.secondary,
                ),
                onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
              ),
            ),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _confirmPasswordController,
            obscureText: _obscureConfirmPassword,
            style: FansivibeTypography.bodyLargeWithFamily,
            decoration: _inputDecoration(
              hint: 'Confirm Password',
              icon: Icons.lock_reset_rounded,
              suffixIcon: IconButton(
                icon: Icon(
                  _obscureConfirmPassword
                      ? Icons.visibility_outlined
                      : Icons.visibility_off_outlined,
                  size: 20,
                  color: FansivibeColors.secondary,
                ),
                onPressed: () => setState(
                  () => _obscureConfirmPassword = !_obscureConfirmPassword,
                ),
              ),
            ),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _nameController,
            style: FansivibeTypography.bodyLargeWithFamily,
            decoration: _inputDecoration(
              hint: 'Your name (optional)',
              icon: Icons.person_outline_rounded,
            ),
          ),
          const SizedBox(height: 20),
          FansiButton.primary(
            label: _submitting ? 'Creating account…' : 'Create Account',
            icon: Icons.arrow_forward_rounded,
            onPressed: _submitting ? null : _onCreateAccountWithEmail,
          ),
        ],
      ),
    );
  }

  InputDecoration _inputDecoration({
    required String hint,
    required IconData icon,
    Widget? suffixIcon,
  }) {
    return InputDecoration(
      hintText: hint,
      hintStyle: FansivibeTypography.bodyMediumWithFamily.copyWith(
        color: FansivibeColors.secondary.withValues(alpha: 0.6),
      ),
      prefixIcon: Icon(icon, color: FansivibeColors.secondary, size: 20),
      suffixIcon: suffixIcon,
      filled: true,
      fillColor: FansivibeColors.surfaceContainerHigh.withValues(alpha: 0.6),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
      border: OutlineInputBorder(
        borderRadius: FansivibeRadius.smdBorder,
        borderSide: BorderSide(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: FansivibeRadius.smdBorder,
        borderSide: BorderSide(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: FansivibeRadius.smdBorder,
        borderSide: const BorderSide(
          color: FansivibeColors.primary,
          width: 1.5,
        ),
      ),
    );
  }

  Widget _buildSignInSwitchFooter() {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              'Already have an account? ',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                fontSize: 14,
              ),
            ),
            GestureDetector(
              onTap: _onNavigateToSignIn,
              child: Text(
                'Sign In',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                  decoration: TextDecoration.underline,
                  decorationColor: FansivibeColors.primary,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildGuestTertiaryOption() {
    return FansiButton.tertiary(
      label: 'Maybe Later — Explore as Guest',
      onPressed: _onMaybeLater,
    );
  }
}

class _SocialAuthButton extends StatelessWidget {
  const _SocialAuthButton({
    required this.label,
    required this.icon,
    required this.onPressed,
    this.isHighlighted = false,
    this.trailing,
  });

  final String label;
  final Widget icon;
  final VoidCallback? onPressed;
  final bool isHighlighted;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          backgroundColor: isHighlighted
              ? FansivibeColors.surfaceContainerHigh
              : FansivibeColors.surfaceContainerLow,
          foregroundColor: FansivibeColors.onSurface,
          side: BorderSide(
            color: isHighlighted
                ? FansivibeColors.primary.withValues(alpha: 0.6)
                : FansivibeColors.outlineVariant.withValues(alpha: 0.4),
            width: 1.2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.fullBorder,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 20),
        ),
        child: Row(
          children: [
            icon,
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                  color: FansivibeColors.onSurface,
                  letterSpacing: 0.2,
                ),
              ),
            ),
            if (trailing != null) trailing!,
          ],
        ),
      ),
    );
  }
}
