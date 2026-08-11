import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';

void main() {
  group('HairstyleRecommendation JSON', () {
    test('round-trips through JSON', () {
      final rec = HairstyleAnalysisResult.mock.topRecommendation;

      final decoded = HairstyleRecommendation.fromJson(rec.toJson());

      expect(decoded.id, rec.id);
      expect(decoded.name, rec.name);
      expect(decoded.description, rec.description);
      expect(decoded.matchScore, rec.matchScore);
      expect(decoded.reasons, rec.reasons);
      expect(decoded.stylingTips, rec.stylingTips);
      expect(decoded.maintenance, rec.maintenance);
      expect(decoded.bestFor, rec.bestFor);
    });
  });

  group('HairstyleAnalysisResult JSON', () {
    test('round-trips through JSON', () {
      final result = HairstyleAnalysisResult.mock;

      final decoded = HairstyleAnalysisResult.fromRunResult(result.toJson());

      expect(decoded.faceShape, result.faceShape);
      expect(decoded.skinTone, result.skinTone);
      expect(decoded.topRecommendation.name, result.topRecommendation.name);
      expect(decoded.alternatives.length, result.alternatives.length);
    });

    test('maps the wire run result shape', () {
      final wire = {
        'appearance': {
          'faceShape': 'Round',
          'skinTone': 'Cool Fair',
          'styleType': 'Classic',
        },
        'recommendations': {
          'top': {
            'id': 'classic_pompadour',
            'name': 'Classic Pompadour',
            'description': 'A timeless pompadour.',
            'matchScore': 0.91,
            'reasons': ['Adds height and balance'],
            'stylingTips': 'Blow-dry back and up.',
            'maintenance': 'High',
            'bestFor': 'Round, Square',
          },
          'alternatives': [
            {
              'id': 'side_part',
              'name': 'Side Part',
              'description': 'A refined side part.',
              'matchScore': 0.8,
              'reasons': ['Adds asymmetry'],
              'stylingTips': 'Part deeply.',
              'maintenance': 'Low',
              'bestFor': 'Oval, Square',
            },
          ],
        },
      };

      final result = HairstyleAnalysisResult.fromRunResult(wire);

      expect(result.faceShape, 'Round');
      expect(result.skinTone, 'Cool Fair');
      expect(result.styleDna, 'Classic');
      expect(result.topRecommendation.name, 'Classic Pompadour');
      expect(result.topRecommendation.matchScore, 0.91);
      expect(result.alternatives.single.name, 'Side Part');
    });
  });

  group('AnalysisRun', () {
    test('parses a completed run', () {
      final run = AnalysisRun.fromJson(<String, dynamic>{
        'run_id': 'run-123',
        'run_type': 'hairstyle',
        'status': 'completed',
        'created_at': '2026-08-11T10:00:00Z',
        'completed_at': '2026-08-11T10:00:05Z',
        'result': <String, dynamic>{'appearance': <String, dynamic>{}},
      });

      expect(run.runId, 'run-123');
      expect(run.runType, 'hairstyle');
      expect(run.isCompleted, isTrue);
      expect(run.result, isNotNull);
    });

    test('is not completed while pending', () {
      final run = AnalysisRun.fromJson({'run_id': 'run-1', 'status': 'pending'});

      expect(run.isCompleted, isFalse);
      expect(run.result, isNull);
    });
  });

  group('hairstyleResultFromRun', () {
    test('parses the run result when present', () {
      final run = AnalysisRun.fromJson(<String, dynamic>{
        'run_id': 'run-1',
        'status': 'completed',
        'result': {
          'appearance': {'faceShape': 'Oval'},
          'recommendations': {
            'top': {
              'id': 'textured_quiff',
              'name': 'Textured Quiff',
              'matchScore': 0.94,
              'reasons': <String>[],
            },
          },
          'alternatives': <Map<String, dynamic>>[],
        },
      });

      final result = hairstyleResultFromRun(run);

      expect(result.faceShape, 'Oval');
      expect(result.topRecommendation.name, 'Textured Quiff');
    });

    test('falls back to the mock result when missing', () {
      final run = AnalysisRun.fromJson({'run_id': 'run-1', 'status': 'pending'});

      final result = hairstyleResultFromRun(run);

      expect(result.faceShape, HairstyleAnalysisResult.mock.faceShape);
    });
  });
}
