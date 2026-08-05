import 'package:flutter/material.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class SavedLooksScreen extends StatelessWidget {
  const SavedLooksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final looks = ProfileMockData.savedLooks;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Saved Looks'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;

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
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 8),
                        Text(
                          '${looks.length} Saved Looks',
                          style: theme.textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Your curated style collection',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        ...looks.map(
                          (look) => Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: _SavedLookCard(look: look),
                          ),
                        ),
                        const SizedBox(height: 32),
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
}

class _SavedLookCard extends StatelessWidget {
  const _SavedLookCard({required this.look});

  final SavedLookDetail look;

  @override
  Widget build(BuildContext context) {
    return FansiHeroCard(
      eyebrow: 'SAVED LOOK',
      image: FansiImageWell(
        icon: Icons.checkroom_rounded,
        color: FansivibeColors.accentGold,
      ),
      badge: FansiBadge(score: look.score),
      title: look.title,
      subtitle: look.date,
      footer: Padding(
        padding: const EdgeInsets.fromLTRB(
          FansivibeSpacing.lg,
          0,
          FansivibeSpacing.lg,
          FansivibeSpacing.lg,
        ),
        child: Text(
          look.items.join(' · '),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.textSecondary,
            height: 1.4,
          ),
        ),
      ),
    );
  }
}
