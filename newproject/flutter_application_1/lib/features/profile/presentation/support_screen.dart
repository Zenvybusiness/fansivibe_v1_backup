import 'package:flutter/material.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class SupportScreen extends StatelessWidget {
  const SupportScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final topics = ProfileMockData.topics;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Support'),
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
                          'Help & Support',
                          style: theme.textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Find answers and get in touch',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        FansivibeCard(
                          child: Column(
                            children: List.generate(topics.length, (i) {
                              final topic = topics[i];
                              return Column(
                                children: [
                                  _SupportTopicTile(topic: topic),
                                  if (i < topics.length - 1)
                                    Divider(
                                      height: 1,
                                      color: FansivibeColors.accentGold
                                          .withValues(alpha: 0.1),
                                      indent: 40,
                                    ),
                                ],
                              );
                            }),
                          ),
                        ),
                        const SizedBox(height: 24),
                        FansivibeCard(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: ListTile(
                              leading: Icon(
                                Icons.mail_rounded,
                                color: FansivibeColors.accentGold,
                              ),
                              title: Text(
                                'Send us a message',
                                style: theme.textTheme.bodyLarge?.copyWith(
                                  fontWeight: FontWeight.w600,
                                  color: FansivibeColors.textPrimary,
                                ),
                              ),
                              subtitle: Text(
                                'We typically respond within 24 hours',
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: FansivibeColors.textSecondary,
                                ),
                              ),
                              trailing: Icon(
                                Icons.chevron_right_rounded,
                                color: FansivibeColors.textSecondary,
                              ),
                              onTap: () {},
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

class _SupportTopicTile extends StatelessWidget {
  const _SupportTopicTile({required this.topic});

  final SupportTopic topic;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return InkWell(
      onTap: () {},
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 4),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(
                _getIcon(topic.iconName),
                size: 20,
                color: FansivibeColors.accentGold,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    topic.title,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: FansivibeColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    topic.description,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.chevron_right_rounded,
              size: 20,
              color: FansivibeColors.textSecondary,
            ),
          ],
        ),
      ),
    );
  }

  IconData _getIcon(String name) {
    switch (name) {
      case 'rocket_launch_rounded':
        return Icons.rocket_launch_rounded;
      case 'bar_chart_rounded':
        return Icons.bar_chart_rounded;
      case 'checkroom_rounded':
        return Icons.checkroom_rounded;
      case 'security_rounded':
        return Icons.security_rounded;
      case 'bug_report_rounded':
        return Icons.bug_report_rounded;
      case 'mail_rounded':
        return Icons.mail_rounded;
      default:
        return Icons.help_outline_rounded;
    }
  }
}
