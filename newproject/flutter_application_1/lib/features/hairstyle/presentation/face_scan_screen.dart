import 'package:flutter/material.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_processing_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class FaceScanScreen extends StatelessWidget {
  const FaceScanScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Face Scan'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
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

                        const FacePreviewPlaceholder(),

                        const SizedBox(height: 20),

                        _buildCheckRow(),
                        const SizedBox(height: 24),

                        _buildStartScanButton(context),
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

  Widget _buildCheckRow() {
    final checks = FaceScanCheck.mockChecks;
    final failingMessage = checks
        .where((c) => !c.isPassing)
        .firstOrNull
        ?.message;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: checks
                .map(
                  (check) => Expanded(
                    child: HairstyleCheckIndicator(
                      label: check.label,
                      isPassing: check.isPassing,
                    ),
                  ),
                )
                .toList(),
          ),
          if (failingMessage != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Icon(
                  Icons.info_outline_rounded,
                  size: 14,
                  color: FansivibeColors.accentGold.withValues(alpha: 0.7),
                ),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    failingMessage,
                    style: TextStyle(
                      color: FansivibeColors.accentGold.withValues(alpha: 0.7),
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildStartScanButton(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: () => _handleScan(context),
        icon: const Icon(Icons.face_rounded, size: 20),
        label: const Text('Start Scan'),
        style: FilledButton.styleFrom(
          backgroundColor: FansivibeColors.accentGold,
          foregroundColor: FansivibeColors.background,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          elevation: 4,
          shadowColor: FansivibeColors.accentGold.withValues(alpha: 0.3),
        ),
      ),
    );
  }

  void _handleScan(BuildContext context) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (_) => const FaceProcessingScreen()),
    );
  }
}
