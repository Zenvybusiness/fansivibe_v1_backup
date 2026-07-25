import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class GlassContainer extends StatelessWidget {
  final Widget child;
  final double? height;
  final double? width;
  final EdgeInsetsGeometry? padding;
  final double blur;
  final double opacity;
  final Color? baseColor;
  final BorderRadius? borderRadius;

  const GlassContainer({
    required this.child,
    this.height,
    this.width,
    this.padding,
    this.blur = 12,
    this.opacity = 0.15,
    this.baseColor,
    this.borderRadius,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: borderRadius ?? FansivibeRadius.lgBorder,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: Container(
          height: height,
          width: width,
          padding: padding ?? const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: (baseColor ?? Colors.white).withValues(alpha: opacity),
            borderRadius: borderRadius ?? FansivibeRadius.lgBorder,
          ),
          child: child,
        ),
      ),
    );
  }
}
