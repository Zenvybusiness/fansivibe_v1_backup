import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/features/hairstyle/domain/face_scan_votes.dart';

/// Unit contract for the deterministic multi-angle aggregation
/// (face_scan_votes.dart): majority vote over real backend runs, explicit
/// ambiguity otherwise. No mocks of the decision itself — hand-built runs.
AnalysisRun _run(String label, {String status = 'completed'}) {
  return AnalysisRun(
    runId: 'run-$label',
    runType: 'hairstyle',
    status: status,
    result: {
      'appearance': {'faceShape': label},
      'confidence': 0.8,
    },
  );
}

void main() {
  group('aggregateFaceScanVotes', () {
    test('unanimous views return the first run', () {
      final a = _run('oval');
      final winner = aggregateFaceScanVotes([a, _run('Oval'), _run('OVAL')]);

      expect(winner, same(a));
    });

    test('2-of-3 majority wins and ships that view verbatim', () {
      final majority = _run('round');
      final winner = aggregateFaceScanVotes([_run('oval'), majority, _run('Round')]);

      expect(winner, same(majority));
    });

    test('fewer than 2 valid views is an explicit miss', () {
      expect(aggregateFaceScanVotes([_run('oval'), null, null]), isNull);
      expect(aggregateFaceScanVotes([null, null, null]), isNull);
    });

    test('invalid labels are discarded, never voted', () {
      expect(
        aggregateFaceScanVotes([_run(''), _run('no_face'), _run('ambiguous')]),
        isNull,
      );
      // One real vote is not enough on its own.
      expect(
        aggregateFaceScanVotes([_run('oval'), _run('no_face'), _run('')]),
        isNull,
      );
    });

    test('failed runs never vote', () {
      expect(
        aggregateFaceScanVotes([
          _run('oval', status: 'failed'),
          _run('oval', status: 'failed'),
          _run('oval'),
        ]),
        isNull,
      );
    });

    test('three-way disagreement is explicit ambiguity', () {
      expect(
        aggregateFaceScanVotes([_run('oval'), _run('round'), _run('square')]),
        isNull,
      );
    });
  });
}
