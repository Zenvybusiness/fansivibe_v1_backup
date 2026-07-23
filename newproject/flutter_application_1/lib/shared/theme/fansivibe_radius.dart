import 'package:flutter/material.dart';

/// Radius tokens for the Fansivibe design system.
///
/// sm  – 0.5 rem  (8 px)  – chips, small tags.
/// md  – 1.5 rem  (24 px) – secondary containers.
/// lg  – 2 rem    (32 px) – primary containers, cards.
/// full            (999)   – pills, primary CTAs.
abstract final class FansivibeRadius {
  FansivibeRadius._();

  static const double sm = 8;
  static const double md = 24;
  static const double lg = 32;
  static const double full = 999;

  // ── Pre-built border-radius objects ──
  static BorderRadius get smBorder => BorderRadius.circular(sm);
  static BorderRadius get mdBorder => BorderRadius.circular(md);
  static BorderRadius get lgBorder => BorderRadius.circular(lg);
  static BorderRadius get fullBorder => BorderRadius.circular(full);
}
