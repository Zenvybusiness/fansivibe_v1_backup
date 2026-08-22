import 'package:flutter/material.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class SavedLooksScreen extends StatefulWidget {
  const SavedLooksScreen({super.key, this.groomingService, this.hairstyleService});

  /// Injectable for tests; when null the screen auto-creates both services.
  final GroomingService? groomingService;
  final HairstyleService? hairstyleService;

  @override
  State<SavedLooksScreen> createState() => _SavedLooksScreenState();
}

class _SavedLooksScreenState extends State<SavedLooksScreen> {
  late final GroomingService _groomingService;
  late final HairstyleService _hairstyleService;
  bool _ownsGroomingService = false;
  bool _ownsHairstyleService = false;
  List<dynamic> _looks = [];

  @override
  void initState() {
    super.initState();
    final groomingProvided = widget.groomingService;
    final hairstyleProvided = widget.hairstyleService;

    if (groomingProvided != null) {
      _groomingService = groomingProvided;
      _ownsGroomingService = false;
    } else {
      _groomingService = GroomingService()..attachLearning(LearningService.instance);
      _ownsGroomingService = true;
    }

    if (hairstyleProvided != null) {
      _hairstyleService = hairstyleProvided;
      _ownsHairstyleService = false;
    } else {
      _hairstyleService = HairstyleService();
      _ownsHairstyleService = true;
    }

    _loadSavedLooks();
  }

  @override
  void dispose() {
    if (_ownsGroomingService) {
      _groomingService.dispose();
    }
    if (_ownsHairstyleService) {
      _hairstyleService.dispose();
    }
    super.dispose();
  }

  Future<void> _loadSavedLooks() async {
    final groomingLooks = await _groomingService.listSavedLooks();
    final hairstyleLooks = await _hairstyleService.listSavedLooks();

    if (!mounted) return;

    setState(() {
      _looks = [...groomingLooks, ...hairstyleLooks];
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

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
          '${_looks.length} Saved Looks',
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
        ..._looks.map(
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

  final dynamic look;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // Determine if this is a grooming or hairstyle saved look
    final sourceContext = look['sourceContext'] as String? ?? '';

    return FansiHeroCard(
      eyebrow: sourceContext == 'grooming' ? 'GROOMING LOOK' : 'HAIRSTYLE LOOK',
      image: FansiImageWell(
        icon: sourceContext == 'grooming' ? Icons.spa_rounded : Icons.face_rounded,
        color: sourceContext == 'grooming' ? FansivibeColors.accentGold : FansivibeColors.success,
      ),
      badge: FansiBadge(score: _computeScore(look)),
      title: look['title'] as String? ?? 'Untitled',
      subtitle: look['sourceRunId'] != null ? 'From run ${look['sourceRunId']}' : null,
      footer: Padding(
        padding: const EdgeInsets.fromLTRB(
          FansivibeSpacing.lg,
          0,
          FansivibeSpacing.lg,
          FansivibeSpacing.lg,
        ),
        child: Text(
          _buildFooterText(look),
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

  int _computeScore(dynamic look) {
    final matchScore = look['snapshot']?['matchScore'] as num?;
    if (matchScore != null) {
      return (matchScore * 100).round();
    }
    return 0;
  }

  String _buildFooterText(dynamic look) {
    if (look == null) return '';

    final sourceContext = look['sourceContext'] as String? ?? '';

    if (sourceContext == 'grooming') {
      final description = look['snapshot']?['description'] as String?;
      if (description != null && description.isNotEmpty) {
        return description;
      }
      final reasons = look['snapshot']?['reasons'] as List<dynamic>? ?? const [];
      if (reasons.isNotEmpty) {
        return reasons.first as String;
      }
      return 'Grooming style saved';
    } else {
      final description = look['snapshot']?['description'] as String?;
      if (description != null && description.isNotEmpty) {
        return description;
      }
      final reasons = look['snapshot']?['reasons'] as List<dynamic>? ?? const [];
      if (reasons.isNotEmpty) {
        return reasons.first as String;
      }
      return 'Hairstyle saved';
    }
  }
}