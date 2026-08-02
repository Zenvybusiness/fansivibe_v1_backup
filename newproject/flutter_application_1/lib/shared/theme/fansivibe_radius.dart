import 'package:flutter/material.dart';

/// Radius tokens for the Fansivibe design system.
///
/// xs  – 0.25 rem (4 px)  – tiny indicators, progress bars.
/// sm  – 0.5 rem  (8 px)  – chips, small tags.
/// smd – 0.75 rem (12 px) – inputs, secondary controls, in-card wells.
/// base– 1 rem    (16 px) – secondary containers, image wells.
/// md  – 1.5 rem  (24 px) – primary containers, cards.
/// lg  – 2 rem    (32 px) – hero panels, large surfaces.
/// full            (999)   – pills, primary CTAs.
abstract final class FansivibeRadius {
  FansivibeRadius._();

  static const double xs = 4;
  static const double sm = 8;
  static const double smd = 12;
  static const double base = 16;
  static const double md = 24;
  static const double lg = 32;
  static const double full = 999;

  // ── Pre-built border-radius objects ──
  static BorderRadius get xsBorder => BorderRadius.circular(xs);
  static BorderRadius get smBorder => BorderRadius.circular(sm);
  static BorderRadius get smdBorder => BorderRadius.circular(smd);
  static BorderRadius get baseBorder => BorderRadius.circular(base);
  static BorderRadius get mdBorder => BorderRadius.circular(md);
  static BorderRadius get lgBorder => BorderRadius.circular(lg);
  static BorderRadius get fullBorder => BorderRadius.circular(full);
}
