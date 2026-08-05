import 'package:flutter/material.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class ColorPaletteDisplay extends StatelessWidget {
  final List<PaletteSwatch> swatches;

  const ColorPaletteDisplay({required this.swatches, super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Your Colour Palette',
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            fontSize: 20,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (int i = 0; i < swatches.length; i++)
                Padding(
                  padding: EdgeInsets.only(
                    right: i < swatches.length - 1
                        ? FansivibeSpacing.sm + 4
                        : 0,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: Color(swatches[i].color),
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.1),
                            width: 1,
                          ),
                        ),
                      ),
                      SizedBox(height: FansivibeSpacing.xs),
                      SizedBox(
                        width: 44,
                        child: Text(
                          swatches[i].label,
                          textAlign: TextAlign.center,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: FansivibeTypography.labelSmallWithFamily
                              .copyWith(fontSize: 9),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
