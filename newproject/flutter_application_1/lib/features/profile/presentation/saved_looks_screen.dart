import 'package:flutter/material.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class SavedLooksScreen extends StatefulWidget {
  const SavedLooksScreen({super.key, this.service});

  /// Injectable for tests; when null a temporary service is created to load
  /// saved looks from the backend.
  final HairstyleService? service;

  @override
  State<SavedLooksScreen> createState() => _SavedLooksScreenState();
}

class _SavedLooksScreenState extends State<SavedLooksScreen> {
  late final HairstyleService _service;
  bool _ownsService = false;
  List<SavedLookDetail>? _looks;

  @override
  void initState() {
    super.initState();
    final provided = widget.service;
    if (provided != null) {
      _service = provided;
    } else {
      _service = HairstyleService();
      _ownsService = true;
    }
    _loadSavedLooks();
  }

  @override
  void dispose() {
    if (_ownsService) {
      _service.dispose();
    }
    super.dispose();
  }

  Future<void> _loadSavedLooks() async {
    final backendLooks = await _service.listSavedLooks();
    if (!mounted) return;

    if (backendLooks.isNotEmpty) {
      setState(() {
        _looks = backendLooks.map(_toDetail).toList();
      });
    } else {
      setState(() {
        _looks = ProfileMockData.savedLooks;
      });
    }
  }

  SavedLookDetail _toDetail(SavedLook look) {
    final snapshot = look.snapshot;
    final matchScore = (snapshot?['matchScore'] as num?)?.toDouble();
    return SavedLookDetail(
      id: look.id,
      title: look.title,
      score: matchScore == null ? 0 : (matchScore * 100).round(),
      date: 'Saved ${_formatMonthDay(look.createdAt)}',
      items: _footerLines(snapshot),
    );
  }

  List<String> _footerLines(Map<String, dynamic>? snapshot) {
    if (snapshot == null) return const [];
    final description = snapshot['description'] as String?;
    if (description != null && description.isNotEmpty) return [description];
    final reasons = snapshot['reasons'] as List<dynamic>? ?? const [];
    return reasons.whereType<String>().toList();
  }

  String _formatMonthDay(DateTime dt) {
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    final month = dt.month >= 1 && dt.month <= 12 ? months[dt.month - 1] : '?';
    return '$month ${dt.day}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final looks = _looks ?? ProfileMockData.savedLooks;

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