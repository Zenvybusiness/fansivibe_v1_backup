import 'dart:async';
import 'package:flutter/material.dart';

/// Callback signature when a product satisfies the telemetry impression threshold:
/// visible in the viewport by at least 50% for at least 1000ms continuously.
typedef OnProductImpression = void Function({
  required String productId,
  required String surface,
  int? position,
  required double visibilityRatio,
  required int dwellMs,
});

/// A non-intrusive wrapper that detects continuous viewport visibility for a product card.
///
/// Triggers [onImpression] exactly once per product per session when:
/// 1. Visibility ratio >= [visibilityThreshold] (default 0.5, i.e. 50%).
/// 2. Dwell duration >= [dwellDuration] (default 1000ms, i.e. 1 continuous second).
/// 3. Visibility did not drop below the threshold during the dwell window.
class ProductImpressionDetector extends StatefulWidget {
  const ProductImpressionDetector({
    super.key,
    required this.productId,
    required this.surface,
    this.position,
    required this.onImpression,
    this.isAlreadyImpressed = false,
    this.dwellDuration = const Duration(milliseconds: 1000),
    this.visibilityThreshold = 0.5,
    required this.child,
  });

  final String productId;
  final String surface;
  final int? position;
  final OnProductImpression onImpression;
  final bool isAlreadyImpressed;
  final Duration dwellDuration;
  final double visibilityThreshold;
  final Widget child;

  @override
  State<ProductImpressionDetector> createState() =>
      _ProductImpressionDetectorState();
}

class _ProductImpressionDetectorState extends State<ProductImpressionDetector> {
  Timer? _dwellTimer;
  ScrollPosition? _scrollPosition;
  bool _impressed = false;

  @override
  void initState() {
    super.initState();
    _impressed = widget.isAlreadyImpressed;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _checkVisibility();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final newPosition = Scrollable.maybeOf(context)?.position;
    if (newPosition != _scrollPosition) {
      _scrollPosition?.removeListener(_onScroll);
      _scrollPosition = newPosition;
      _scrollPosition?.addListener(_onScroll);
    }
  }

  @override
  void didUpdateWidget(ProductImpressionDetector oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isAlreadyImpressed && !_impressed) {
      _impressed = true;
      _cancelTimer();
    }
    if (oldWidget.productId != widget.productId) {
      _impressed = widget.isAlreadyImpressed;
      _cancelTimer();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _checkVisibility();
      });
    }
  }

  @override
  void dispose() {
    _cancelTimer();
    _scrollPosition?.removeListener(_onScroll);
    super.dispose();
  }

  void _onScroll() {
    _checkVisibility();
  }

  void _cancelTimer() {
    _dwellTimer?.cancel();
    _dwellTimer = null;
  }

  double _calculateVisibilityRatio() {
    if (!mounted) return 0.0;
    final renderBox = context.findRenderObject() as RenderBox?;
    if (renderBox == null || !renderBox.hasSize || !renderBox.attached) {
      return 0.0;
    }
    final boxSize = renderBox.size;
    if (boxSize.width <= 0 || boxSize.height <= 0) return 0.0;

    final totalArea = boxSize.width * boxSize.height;

    Rect visibleBounds;
    final scrollable = Scrollable.maybeOf(context);
    if (scrollable != null &&
        scrollable.context.findRenderObject() is RenderBox) {
      final scrollBox = scrollable.context.findRenderObject() as RenderBox;
      if (!scrollBox.hasSize || !scrollBox.attached) return 0.0;
      final scrollBoxPos = scrollBox.localToGlobal(Offset.zero);
      visibleBounds = Rect.fromLTWH(
        scrollBoxPos.dx,
        scrollBoxPos.dy,
        scrollBox.size.width,
        scrollBox.size.height,
      );
    } else {
      final mediaQuery = MediaQuery.maybeOf(context);
      final screenSize = mediaQuery?.size ?? const Size(1000, 2000);
      visibleBounds = Rect.fromLTWH(0, 0, screenSize.width, screenSize.height);
    }

    final itemPos = renderBox.localToGlobal(Offset.zero);
    final itemRect = Rect.fromLTWH(
      itemPos.dx,
      itemPos.dy,
      boxSize.width,
      boxSize.height,
    );

    if (itemRect.right <= visibleBounds.left ||
        itemRect.left >= visibleBounds.right ||
        itemRect.bottom <= visibleBounds.top ||
        itemRect.top >= visibleBounds.bottom) {
      return 0.0;
    }

    final intersection = itemRect.intersect(visibleBounds);
    final visibleArea = intersection.width * intersection.height;
    return (visibleArea / totalArea).clamp(0.0, 1.0);
  }

  void _checkVisibility() {
    if (_impressed || !mounted) return;

    final ratio = _calculateVisibilityRatio();
    if (ratio >= widget.visibilityThreshold) {
      _dwellTimer ??= Timer(widget.dwellDuration, () {
        if (!mounted || _impressed) return;
        final finalRatio = _calculateVisibilityRatio();
        if (finalRatio >= widget.visibilityThreshold) {
          _impressed = true;
          _cancelTimer();
          widget.onImpression(
            productId: widget.productId,
            surface: widget.surface,
            position: widget.position,
            visibilityRatio: (finalRatio * 100).round() / 100.0,
            dwellMs: widget.dwellDuration.inMilliseconds,
          );
        } else {
          _cancelTimer();
        }
      });
    } else {
      _cancelTimer();
    }
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}
