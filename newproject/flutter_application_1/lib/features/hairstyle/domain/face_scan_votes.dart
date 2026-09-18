import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';

/// Deterministic multi-angle aggregation contract (no LLM vote).
///
/// Each of the FRONT/LEFT/RIGHT captures is analyzed through the existing
/// single-image endpoint, so every vote is a real backend measurement.
/// Aggregation is mechanical:
///
/// - A view is valid only when its run `completed` and its
///   `appearance.faceShape` is a real label. Empty, `no_face`, and
///   `ambiguous` views are discarded (never counted as votes).
/// - At least 2 of 3 valid views are required — otherwise null
///   (explicit "not enough clear views", never a guess).
/// - The majority label wins. The returned run is the first completed
///   run carrying it, so its backend recommendations ship verbatim and
///   the displayed confidence is that run's own backend confidence —
///   never an invented mean or blend.
/// - Equal top counts (e.g. three distinct labels) are explicit
///   ambiguity → null. No accuracy is claimed beyond the votes.
AnalysisRun? aggregateFaceScanVotes(List<AnalysisRun?> runs) {
  const invalidLabels = {'', 'no_face', 'ambiguous'};
  final valid = <AnalysisRun>[];
  for (final run in runs) {
    if (run == null || !run.isCompleted) continue;
    final appearance =
        run.result?['appearance'] as Map<String, dynamic>?;
    final label = (appearance?['faceShape'] as String? ?? '').trim();
    if (invalidLabels.contains(label.toLowerCase())) continue;
    valid.add(run);
  }
  if (valid.length < 2) return null;

  final counts = <String, int>{};
  for (final run in valid) {
    final appearance =
        run.result?['appearance'] as Map<String, dynamic>?;
    final label =
        ((appearance?['faceShape'] as String?) ?? '').trim().toLowerCase();
    counts[label] = (counts[label] ?? 0) + 1;
  }
  var bestLabel = '';
  var bestCount = 0;
  var tied = false;
  for (final entry in counts.entries) {
    if (entry.value > bestCount) {
      bestLabel = entry.key;
      bestCount = entry.value;
      tied = false;
    } else if (entry.value == bestCount) {
      tied = true;
    }
  }
  if (tied) return null;
  for (final run in valid) {
    final appearance =
        run.result?['appearance'] as Map<String, dynamic>?;
    final label =
        ((appearance?['faceShape'] as String?) ?? '').trim().toLowerCase();
    if (label == bestLabel) return run;
  }
  return null;
}
