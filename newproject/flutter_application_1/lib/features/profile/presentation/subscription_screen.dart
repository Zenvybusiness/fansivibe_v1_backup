import 'package:flutter/material.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class SubscriptionScreen extends StatelessWidget {
  const SubscriptionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final plans = ProfileMockData.plans;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Subscription'),
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
                          'Choose Your Plan',
                          style: theme.textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Unlock premium style features',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        ...plans.map(
                          (plan) => Padding(
                            padding: const EdgeInsets.only(bottom: 16),
                            child: _PlanCard(plan: plan),
                          ),
                        ),
                        const SizedBox(height: 16),
                        Center(
                          child: Text(
                            'Cancel anytime · No hidden fees',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.textSecondary,
                            ),
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

class _PlanCard extends StatelessWidget {
  const _PlanCard({required this.plan});

  final SubscriptionPlan plan;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return FansivibeCard(
      borderColor: plan.isPopular
          ? FansivibeColors.accentGold
          : FansivibeColors.accentGold.withValues(alpha: 0.2),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                plan.name,
                style: theme.textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.textPrimary,
                ),
              ),
              if (plan.isPopular)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: FansivibeColors.accentGold,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    'Popular',
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: FansivibeColors.background,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                plan.price,
                style: theme.textTheme.displayLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.accentGold,
                  fontSize: 36,
                ),
              ),
              const SizedBox(width: 4),
              Text(
                plan.period,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Divider(
            height: 1,
            color: FansivibeColors.accentGold.withValues(alpha: 0.1),
          ),
          const SizedBox(height: 16),
          ...plan.features.map(
            (feature) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  Icon(
                    Icons.check_circle_rounded,
                    size: 18,
                    color: FansivibeColors.accentGold,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      feature,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () {},
              style: ElevatedButton.styleFrom(
                backgroundColor: plan.isPopular
                    ? FansivibeColors.accentGold
                    : FansivibeColors.accentGold.withValues(alpha: 0.1),
                foregroundColor: plan.isPopular
                    ? FansivibeColors.background
                    : FansivibeColors.accentGold,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                  side: plan.isPopular
                      ? BorderSide.none
                      : BorderSide(
                          color: FansivibeColors.accentGold.withValues(
                            alpha: 0.3,
                          ),
                        ),
                ),
              ),
              child: Text(
                plan.name == 'Free' ? 'Current Plan' : 'Subscribe',
                style: theme.textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
