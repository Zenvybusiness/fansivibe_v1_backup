import 'dart:math';
import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class AnimatedScoreCounter extends StatefulWidget {
  final int targetScore;
  final double fontSize;
  final Duration duration;

  const AnimatedScoreCounter({
    required this.targetScore,
    this.fontSize = 72,
    this.duration = const Duration(milliseconds: 800),
    super.key,
  });

  @override
  State<AnimatedScoreCounter> createState() => _AnimatedScoreCounterState();
}

class _AnimatedScoreCounterState extends State<AnimatedScoreCounter>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: widget.duration);
    _animation = CurvedAnimation(parent: _controller, curve: Curves.easeOut);
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Color _scoreColor(int score) {
    if (score >= 90) return FansivibeColors.success;
    if (score >= 70) return FansivibeColors.primary;
    if (score >= 50) return FansivibeColors.warning;
    return FansivibeColors.error;
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        final current = (widget.targetScore * _animation.value).round();
        final display = min(current, widget.targetScore);
        return Text(
          '$display',
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: widget.fontSize,
            color: _scoreColor(widget.targetScore),
            fontWeight: FontWeight.w600,
          ),
        );
      },
    );
  }
}
