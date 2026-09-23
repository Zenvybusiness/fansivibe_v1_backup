// ignore_for_file: avoid_print, prefer_interpolation_to_compose_strings
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_client.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';
import 'package:fansivibe/features/knowledge/presentation/view_models/fashion_reasoning_view_model.dart';

void main() {
  test('Phase 3AK Live client-to-backend smoke test', () async {
    print('=' * 60);
    print('PHASE 3AK LIVE CLIENT-TO-BACKEND SMOKE TEST');
    print('Connecting to live FastAPI backend at http://localhost:8000/v1/reasoning');
    print('Pipeline: Flutter UI ViewModel -> Repository -> Client -> HTTP -> Backend -> Ollama -> Typed Models -> Presentation State');
    print('=' * 60);

    final client = KnowledgeClient();
    final repo = KnowledgeRepositoryImpl(client: client);
    final viewModel = FashionReasoningViewModel(repository: repo);

    final testCases = [
      {'name': 'supported_explanation', 'query': 'what is denim', 'intent': 'explain'},
      {'name': 'comparison', 'query': 'cotton vs linen', 'intent': 'compare'},
      {'name': 'styling_matching', 'query': 'white sneakers', 'intent': 'match'},
      {'name': 'insufficient_evidence', 'query': 'kimono sizing', 'intent': 'explain'},
      {'name': 'unsupported_info', 'query': 'current price of white sneakers', 'intent': 'match'},
    ];

    final results = <Map<String, dynamic>>[];

    for (final testCase in testCases) {
      final name = testCase['name']!;
      final query = testCase['query']!;
      final intent = testCase['intent'];

      print('\n---> Executing Query: "$query" (test: $name)');
      final stopwatch = Stopwatch()..start();

      await viewModel.queryReasoning(query, intent: intent);

      stopwatch.stop();
      final elapsedSec = stopwatch.elapsedMilliseconds / 1000.0;
      final state = viewModel.state;

      final isTyped = state.response != null || state.failure != null;

      // Check if internal IDs leak into user prose (answer, reasoning note, error message)
      final checkTexts = [
        state.response?.answer ?? '',
        ...state.conclusions.map((c) => c.statement),
        ...state.conclusions.map((c) => c.reasoningNote),
        state.errorMessage ?? '',
      ].join(' ');

      final internalIdLeak = RegExp(r'\b(term-|alias-|rel-|rule-)[a-z0-9_-]+\b')
          .hasMatch(checkTexts);

      print('Elapsed: ${elapsedSec.toStringAsFixed(2)}s');
      print('UI Status: ${state.status}');
      print('Typed Response Present: ${state.response != null}');
      if (state.response != null) {
        print('Answer: ${state.response!.answer}');
        print('Confidence: ${state.confidence}');
        print('Unsupported: ${state.response!.unsupported}');
        print('Conclusions: ${state.conclusions.length}');
        for (int i = 0; i < state.conclusions.length; i++) {
          final c = state.conclusions[i];
          print('  [$i] ${c.statement} [${c.standing}] (citations: ${c.evidenceIds.length})');
        }
        print('Missing Evidence: ${state.missingEvidence}');
        print('Uncertainties: ${state.uncertainties}');
      }
      if (state.isError) {
        print('Technical Failure: ${state.failure}');
        print('UI Error Message: ${state.errorMessage}');
      }
      print('Internal IDs Leaked as Prose: $internalIdLeak');

      results.add({
        'name': name,
        'query': query,
        'elapsed_s': elapsedSec,
        'ui_status': state.status.name,
        'is_typed': isTyped,
        'internal_ids_leaked': internalIdLeak,
        'has_response': state.response != null,
        'failure': state.failure?.name,
        'error_message': state.errorMessage,
        'answer_preview': state.response?.answer,
        'conclusions_count': state.conclusions.length,
        'unsupported': state.response?.unsupported,
        'missing_evidence_count': state.missingEvidence.length,
      });
    }

    print('\n' + '=' * 60);
    print('LIVE CLIENT SMOKE TEST SUMMARY:');
    for (final r in results) {
      print('  ${r['name']} ("${r['query']}"): UI=${r['ui_status']}, typed=${r['is_typed']}, leaked_ids=${r['internal_ids_leaked']} (${r['elapsed_s'].toStringAsFixed(2)}s)');
    }
    print('=' * 60);

    final outputFile = File('live_flutter_smoke_results.json');
    await outputFile.writeAsString(const JsonEncoder.withIndent('  ').convert(results));
    print('\nResults saved to ${outputFile.path}');

    // Verify assertions
    expect(results.length, 5);
    for (final r in results) {
      expect(r['is_typed'], isTrue);
      expect(r['internal_ids_leaked'], isFalse);
    }
  }, timeout: const Timeout(Duration(minutes: 5)));
}
