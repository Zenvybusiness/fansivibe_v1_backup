import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/discover.dart';
import 'package:fansivibe/features/discover/presentation/widgets/look_details_widgets.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// The Look Details screen (DISCOVER-002, M14).
///
/// Backend-first over #44 `GET /v1/looks/{look_id}`: the screen takes a
/// backend catalog code and fetches the detail verbatim. Loading,
/// not-found (unknown code), and failure states are truthful with retry;
/// nothing renders until the backend answers.
///
/// Only grounded catalog fields render (title, description, match score,
/// reasons, styling tips, maintenance, best-for). The catalog carries no
/// image, occasion/style/fit tags, ensemble, wardrobe alternatives, or
/// trending signal, so those sections do not exist here (AI-0 honesty).
/// There is no save affordance: persisting a discover look has no
/// mapping decision (DEC-013 forbids wiring mock ids to the save
/// surface), so no fake local save is offered.
class LookDetailsScreen extends StatefulWidget {
  const LookDetailsScreen({required this.lookId, this.repository, super.key});

  /// Backend catalog code, verbatim (never a local id).
  final String lookId;

  /// Injectable for tests; when null the screen owns its own repository.
  final DiscoverRepository? repository;

  @override
  State<LookDetailsScreen> createState() => _LookDetailsScreenState();
}

class _LookDetailsScreenState extends State<LookDetailsScreen> {
  late final DiscoverRepository _repository;
  bool _loading = true;
  LookDetail? _detail;
  bool _notFound = false;
  DiscoverFailure? _failure;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? DiscoverRepositoryImpl();
    _fetch();
  }

  Future<void> _fetch() async {
    setState(() {
      _loading = true;
      _notFound = false;
      _failure = null;
    });
    final result = await _repository.getLookDetail(lookId: widget.lookId);
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (result.isAvailable) {
        _detail = result.detail;
      } else if (result.notFound) {
        _notFound = true;
      } else {
        _failure = result.failure;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: FansivibeColors.background,
        elevation: 0,
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          _detail?.title ?? 'Look Details',
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        actions: [
          if (_detail != null)
            IconButton(
              icon: Icon(
                Icons.share_rounded,
                color: FansivibeColors.textSecondary,
              ),
              onPressed: () => _handleShare(context),
            ),
        ],
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 600.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                    ),
                    child: _buildBody(context),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(48),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_notFound) {
      return _buildMessageState(
        context,
        icon: Icons.search_off_rounded,
        title: 'Look not available',
        message: 'This look is no longer in the catalog.',
        actionLabel: 'Go Back',
        onAction: () => Navigator.of(context).pop(),
      );
    }
    if (_failure != null || _detail == null) {
      return _buildMessageState(
        context,
        icon: Icons.cloud_off_rounded,
        title: 'Look unavailable',
        message: 'Check your connection and try again.',
        actionLabel: 'Try Again',
        onAction: _fetch,
      );
    }
    final look = _detail!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 12),
        _buildHeroSection(context, look),
        const SizedBox(height: 24),
        _buildReasonsSection(context, look),
        const SizedBox(height: 24),
        _buildDetailsSection(context, look),
        const SizedBox(height: 24),
        _buildActionsSection(context, look),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _buildMessageState(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String message,
    required String actionLabel,
    required VoidCallback onAction,
  }) {
    final theme = Theme.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(48),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 64,
              color: FansivibeColors.accentGold.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 16),
            Text(
              title,
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              message,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            FansiButton.primary(
              label: actionLabel,
              icon: Icons.refresh_rounded,
              onPressed: onAction,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeroSection(BuildContext context, LookDetail look) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: double.infinity,
          height: 200,
          decoration: BoxDecoration(
            color: FansivibeColors.surface,
            borderRadius: FansivibeRadius.baseBorder,
          ),
          child: Stack(
            fit: StackFit.expand,
            children: [
              Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.checkroom_rounded,
                      size: 48,
                      color: FansivibeColors.accentGold.withValues(alpha: 0.3),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Look Image',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary.withValues(
                          alpha: 0.7,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Positioned(
                top: 12,
                right: 12,
                child: FansiBadge(
                  score: look.matchScore,
                  size: BadgeSize.medium,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        Text(
          look.title,
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          look.description,
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildReasonsSection(BuildContext context, LookDetail look) {
    final theme = Theme.of(context);

    return LookDetailCard(
      title: 'Why This Look Works',
      subtitle: 'Grounded matching reasons',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: look.reasons
            .map(
              (reason) => Padding(
                padding: EdgeInsets.only(
                  bottom: reason == look.reasons.last ? 0 : 12,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          color: FansivibeColors.accentGold,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        reason,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: FansivibeColors.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildDetailsSection(BuildContext context, LookDetail look) {
    final theme = Theme.of(context);

    Widget row(String label, String value, {bool last = false}) {
      return Padding(
        padding: EdgeInsets.only(bottom: last ? 0 : 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label.toUpperCase(),
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textSecondary,
                letterSpacing: 0.5,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              value,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textPrimary,
              ),
            ),
          ],
        ),
      );
    }

    return LookDetailCard(
      title: 'The Details',
      subtitle: 'Styling, care, and best-for',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          row('Styling', look.stylingTips),
          row('Maintenance', look.maintenance),
          row('Best for', look.bestFor, last: true),
        ],
      ),
    );
  }

  Widget _buildActionsSection(BuildContext context, LookDetail look) {
    return Row(
      children: [
        Expanded(
          child: FansiButton.secondary(
            label: 'Share',
            icon: Icons.share_rounded,
            onPressed: () => _handleShare(context),
          ),
        ),
      ],
    );
  }

  void _handleShare(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Share feature coming soon'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }
}
