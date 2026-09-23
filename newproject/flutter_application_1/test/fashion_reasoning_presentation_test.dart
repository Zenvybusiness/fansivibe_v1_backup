import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_client.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';
import 'package:fansivibe/features/knowledge/presentation/models/fashion_reasoning_state.dart';
import 'package:fansivibe/features/knowledge/presentation/view_models/fashion_reasoning_view_model.dart';
import 'package:fansivibe/features/knowledge/presentation/widgets/fashion_reasoning_card.dart';
import 'package:fansivibe/features/knowledge/presentation/widgets/fashion_reasoning_view.dart';
import 'package:fansivibe/features/knowledge/presentation/fashion_reasoning_screen.dart';

Widget _buildTestApp(Widget child) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: child),
  );
}

void main() {
  final sampleVersions = const ReasoningVersions(
    ffoVersion: '1.0',
    corpusDigest: '967f891e4c91d4e9463be5ea183b62ad3f3548f35c1b1e4d8678da49bf4d2581',
    evidenceSchema: 'evidence-pack/1',
    reasoningContractVersion: '2.0',
  );

  final sampleResponse = FashionReasoningResponse(
    answer: 'Denim is a durable cotton twill textile.',
    conclusions: [
      const ReasoningConclusion(
        statement: 'Denim is a durable twill textile.',
        evidenceIds: ['term-denim'],
        ffoRefs: ['denim', 'textile'],
        reasoningNote: 'Grounded in term-denim.',
        standing: 'supported',
      ),
    ],
    uncertainties: const [],
    missingEvidence: const [],
    contradictions: const [],
    confidence: 'high',
    unsupported: false,
    versions: sampleVersions,
  );

  group('Phase 3AK — Fashion Reasoning Presentation Tests', () {
    // 1. Successful reasoning response rendering
    testWidgets('1. successful reasoning response renders answer and conclusions', (tester) async {
      await tester.pumpWidget(
        _buildTestApp(FashionReasoningCard(response: sampleResponse)),
      );

      expect(find.text('Denim is a durable cotton twill textile.'), findsOneWidget);
      expect(find.text('Denim is a durable twill textile.'), findsOneWidget);
      expect(find.text('SUPPORTED'), findsOneWidget);
      expect(find.text('HIGH'), findsOneWidget);
    });

    // 2. Multiple conclusions rendering
    testWidgets('2. multiple conclusions render distinctly', (tester) async {
      final multiResponse = FashionReasoningResponse(
        answer: 'Cotton and linen have contrasting textures.',
        conclusions: [
          const ReasoningConclusion(
            statement: 'Cotton provides soft everyday durability.',
            evidenceIds: ['term-cotton'],
            ffoRefs: ['cotton'],
            reasoningNote: 'Note for cotton.',
            standing: 'supported',
          ),
          const ReasoningConclusion(
            statement: 'Linen offers breathable open weave.',
            evidenceIds: ['term-linen'],
            ffoRefs: ['linen'],
            reasoningNote: 'Note for linen.',
            standing: 'supported',
          ),
          const ReasoningConclusion(
            statement: 'Both are traditional natural fibers.',
            evidenceIds: ['term-cotton', 'term-linen'],
            ffoRefs: ['cotton', 'linen', 'material'],
            reasoningNote: 'Comparison synthesis.',
            standing: 'qualified',
          ),
        ],
        confidence: 'high',
        versions: sampleVersions,
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningCard(response: multiResponse)),
      );

      expect(find.text('Cotton provides soft everyday durability.'), findsOneWidget);
      expect(find.text('Linen offers breathable open weave.'), findsOneWidget);
      expect(find.text('Both are traditional natural fibers.'), findsOneWidget);
      expect(find.text('QUALIFIED'), findsOneWidget);
      expect(find.text('3'), findsOneWidget); // badge count
    });

    // 3. Empty conclusions handling
    testWidgets('3. empty conclusions renders insufficient evidence state', (tester) async {
      final insufficientResponse = FashionReasoningResponse(
        answer: 'No evidence available in the corpus for kimono sizing.',
        conclusions: const [],
        missingEvidence: const ['kimono sizing specifications'],
        confidence: 'low',
        unsupported: false,
        versions: sampleVersions,
      );

      final state = FashionReasoningState(
        status: FashionReasoningStatus.insufficientEvidence,
        response: insufficientResponse,
        query: 'kimono sizing',
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningView(state: state)),
      );

      expect(find.text('Insufficient Evidence'), findsOneWidget);
      expect(find.text('No evidence available in the corpus for kimono sizing.'), findsOneWidget);
      expect(find.text('kimono sizing specifications'), findsOneWidget);
    });

    // 4. Uncertainty rendering
    testWidgets('4. uncertainty list renders explicitly in designated section', (tester) async {
      final uncertainResponse = FashionReasoningResponse(
        answer: 'Grunge aesthetics have contested timeline origins.',
        conclusions: [
          const ReasoningConclusion(
            statement: 'Grunge aesthetic incorporates distressed layering.',
            evidenceIds: ['term-grunge'],
            standing: 'supported',
          ),
        ],
        uncertainties: [
          'Historical overlap between Seattle sound and earlier thrift culture',
          'Regional variance in Pacific Northwest styling adoption',
        ],
        confidence: 'medium',
        versions: sampleVersions,
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningCard(response: uncertainResponse)),
      );

      expect(find.text('Uncertainties & Considerations'), findsOneWidget);
      expect(
        find.text('Historical overlap between Seattle sound and earlier thrift culture'),
        findsOneWidget,
      );
      expect(
        find.text('Regional variance in Pacific Northwest styling adoption'),
        findsOneWidget,
      );
    });

    // 5. Missing evidence rendering
    testWidgets('5. missing evidence renders in dedicated section', (tester) async {
      final missingResponse = FashionReasoningResponse(
        answer: 'Tweed suit care requires fabric-specific maintenance guidelines.',
        conclusions: const [],
        missingEvidence: [
          'dry cleaning temperature constraints',
          'wool brush maintenance frequency',
        ],
        confidence: 'low',
        versions: sampleVersions,
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningCard(response: missingResponse)),
      );

      expect(find.text('What is Missing from Current Sources'), findsOneWidget);
      expect(find.text('dry cleaning temperature constraints'), findsOneWidget);
      expect(find.text('wool brush maintenance frequency'), findsOneWidget);
    });

    // 6. Unsupported=true rendering
    testWidgets('6. unsupported=true renders distinct out-of-scope UI state', (tester) async {
      final unsupportedResponse = FashionReasoningResponse(
        answer: 'Pricing information is outside the scope of the fashion ontology.',
        conclusions: const [],
        missingEvidence: const ['retail pricing data'],
        confidence: 'unknown',
        unsupported: true,
        versions: sampleVersions,
      );

      final state = FashionReasoningState(
        status: FashionReasoningStatus.unsupported,
        response: unsupportedResponse,
        query: 'current price of white sneakers',
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningView(state: state)),
      );

      expect(find.text('Outside Knowledge Scope'), findsOneWidget);
      expect(find.text('Unsupported query domain'), findsOneWidget);
      expect(find.text('Pricing information is outside the scope of the fashion ontology.'), findsOneWidget);
      expect(find.text('retail pricing data'), findsOneWidget);
    });

    // 7. HTTP 422 contract violation
    testWidgets('7. HTTP 422 maps to contractViolation state with truthful message', (tester) async {
      const state = FashionReasoningState(
        status: FashionReasoningStatus.contractViolation,
        failure: ReasoningFailure.contractViolation,
        errorMessage: 'The request could not be processed due to contract constraints.',
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningView(state: state)),
      );

      expect(find.text('Contract Violation'), findsOneWidget);
      expect(find.text('The request could not be processed due to contract constraints.'), findsOneWidget);
    });

    // 8. HTTP 502 AI_FAILURE / malformed output
    testWidgets('8. HTTP 502 maps to malformedInvalidResponse state', (tester) async {
      const state = FashionReasoningState(
        status: FashionReasoningStatus.malformedInvalidResponse,
        failure: ReasoningFailure.malformedOutput,
        errorMessage: 'The reasoning response could not be validated against the fashion knowledge contract.',
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningView(state: state)),
      );

      expect(find.text('Response Validation Failed'), findsOneWidget);
      expect(
        find.text('The reasoning response could not be validated against the fashion knowledge contract.'),
        findsOneWidget,
      );
    });

    // 9. HTTP 503 AI_UNAVAILABLE
    testWidgets('9. HTTP 503 maps to aiUnavailable state with retry option', (tester) async {
      bool retried = false;
      const state = FashionReasoningState(
        status: FashionReasoningStatus.aiUnavailable,
        failure: ReasoningFailure.serviceUnavailable,
        errorMessage: 'The fashion reasoning service is temporarily unavailable. Please try again shortly.',
      );

      await tester.pumpWidget(
        _buildTestApp(
          FashionReasoningView(
            state: state,
            onRetry: () => retried = true,
          ),
        ),
      );

      expect(find.text('AI Service Unavailable'), findsOneWidget);
      expect(
        find.text('The fashion reasoning service is temporarily unavailable. Please try again shortly.'),
        findsOneWidget,
      );
      expect(find.text('Try Again'), findsOneWidget);

      await tester.tap(find.text('Try Again'));
      expect(retried, isTrue);
    });

    // 10. HTTP 504 AI_TIMEOUT
    testWidgets('10. HTTP 504 maps to timeout state', (tester) async {
      const state = FashionReasoningState(
        status: FashionReasoningStatus.timeout,
        failure: ReasoningFailure.timeout,
        errorMessage: 'The reasoning request timed out while analyzing fashion sources. Please try again.',
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningView(state: state)),
      );

      expect(find.text('Request Timed Out'), findsOneWidget);
      expect(
        find.text('The reasoning request timed out while analyzing fashion sources. Please try again.'),
        findsOneWidget,
      );
    });

    // 11. Network failure
    testWidgets('11. network failure maps to apiNetworkError state', (tester) async {
      const state = FashionReasoningState(
        status: FashionReasoningStatus.apiNetworkError,
        failure: ReasoningFailure.networkError,
        errorMessage: 'Unable to reach the reasoning service. Please check your network connection.',
      );

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningView(state: state)),
      );

      expect(find.text('Network Unreachable'), findsOneWidget);
      expect(
        find.text('Unable to reach the reasoning service. Please check your network connection.'),
        findsOneWidget,
      );
    });

    // 12. Loading state
    testWidgets('12. loading state renders fashion analysis indicator', (tester) async {
      const state = FashionReasoningState.loading(query: 'what is denim');

      await tester.pumpWidget(
        _buildTestApp(FashionReasoningView(state: state)),
      );

      expect(find.text('Analyzing Fashion Knowledge'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('Evaluating ontology evidence, styling rules & relationships…'), findsOneWidget);
    });

    // 13. Malformed response handling
    test('13. KnowledgeClient maps malformed 200 JSON to malformedOutput failure', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async => http.Response('not valid json {', 200)),
      );

      final result = await client.reasonQueryDetailed(
        const FashionReasoningRequest(query: 'what is denim'),
      );

      expect(result.isFailure, isTrue);
      expect(result.failure, ReasoningFailure.malformedOutput);
    });

    // 14. Versions parsing and rendering
    testWidgets('14. versions pins parse and display in footer', (tester) async {
      await tester.pumpWidget(
        _buildTestApp(FashionReasoningCard(response: sampleResponse)),
      );

      expect(
        find.text('Verified Fashion Ontology v1.0 • Reasoning Contract v2.0'),
        findsOneWidget,
      );
    });

    // 15. Evidence IDs remain internal
    testWidgets('15. evidence IDs like term-denim do NOT leak as visible prose', (tester) async {
      await tester.pumpWidget(
        _buildTestApp(FashionReasoningCard(response: sampleResponse)),
      );

      expect(find.text('term-denim'), findsNothing);
      expect(find.textContaining('citations'), findsOneWidget);
    });

    // 16. No raw Ollama JSON displayed
    testWidgets('16. raw Ollama JSON never appears in widget tree', (tester) async {
      await tester.pumpWidget(
        _buildTestApp(FashionReasoningCard(response: sampleResponse)),
      );

      expect(find.textContaining('"corpus_digest"'), findsNothing);
      expect(find.textContaining('"evidence_ids"'), findsNothing);
      expect(find.textContaining('"reasoning_contract_version"'), findsNothing);
    });

    // 17. Repository delegation
    test('17. KnowledgeRepositoryImpl reasonQueryDetailed delegates to client', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/reasoning');
          return http.Response(jsonEncode(sampleResponse.toJson()), 200);
        }),
      );
      final repo = KnowledgeRepositoryImpl(client: client);

      final result = await repo.reasonQueryDetailed(
        const FashionReasoningRequest(query: 'what is denim'),
      );

      expect(result.isSuccess, isTrue);
      expect(result.response!.answer, contains('Denim'));
    });

    // 18. Client request serialization
    test('18. FashionReasoningRequest serializes fields according to backend contract', () {
      const req = FashionReasoningRequest(
        query: 'cotton vs linen',
        intent: 'compare',
        maxConclusions: 3,
        evidenceOnly: true,
        context: ReasoningContextDto(
          occasion: 'casual',
          climate: 'summer',
        ),
      );

      final json = req.toJson();
      expect(json['query'], 'cotton vs linen');
      expect(json['intent'], 'compare');
      expect(json['max_conclusions'], 3);
      expect(json['evidence_only'], isTrue);
      expect(json['context']['occasion'], 'casual');
      expect(json['context']['climate'], 'summer');
    });

    // 19. Response deserialization
    test('19. FashionReasoningResponse deserializes complete contract cleanly', () {
      final json = sampleResponse.toJson();
      final parsed = FashionReasoningResponse.fromJson(json);

      expect(parsed.answer, sampleResponse.answer);
      expect(parsed.conclusions.length, 1);
      expect(parsed.conclusions.first.evidenceIds, ['term-denim']);
      expect(parsed.versions.ffoVersion, '1.0');
      expect(parsed.confidence, 'high');
      expect(parsed.unsupported, isFalse);
    });

    // 20. Retry behavior
    test('20. ViewModel retry resubmits the last query to repository', () async {
      int queryCount = 0;
      final mockRepo = _MockKnowledgeRepository(() async {
        queryCount++;
        if (queryCount == 1) {
          return const ReasoningResult.failure(ReasoningFailure.serviceUnavailable);
        }
        return ReasoningResult.success(sampleResponse);
      });

      final viewModel = FashionReasoningViewModel(repository: mockRepo);

      await viewModel.queryReasoning('what is denim');
      expect(queryCount, 1);
      expect(viewModel.state.status, FashionReasoningStatus.aiUnavailable);

      await viewModel.retry();
      expect(queryCount, 2);
      expect(viewModel.state.status, FashionReasoningStatus.success);
      expect(viewModel.state.response!.answer, contains('Denim'));
    });

    // Full screen widget test
    testWidgets('FashionReasoningScreen mounts and executes initialQuery', (tester) async {
      final mockRepo = _MockKnowledgeRepository(() async {
        return ReasoningResult.success(sampleResponse);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: FashionReasoningScreen(
            initialQuery: 'what is denim',
            repository: mockRepo,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Fashion Reasoning'), findsOneWidget);
      expect(find.text('Denim is a durable cotton twill textile.'), findsOneWidget);
    });
  });
}

class _MockKnowledgeRepository implements KnowledgeRepository {
  _MockKnowledgeRepository(this._reasonHandler);

  final Future<ReasoningResult> Function() _reasonHandler;

  @override
  Future<ReasoningResult> reasonQueryDetailed(FashionReasoningRequest request) {
    return _reasonHandler();
  }

  @override
  Future<FashionReasoningResponse?> reasonQuery(FashionReasoningRequest request) async {
    final res = await _reasonHandler();
    return res.response;
  }

  @override
  Future<KnowledgeLookList?> listLooks({int page = 1, int pageSize = 20}) async => null;

  @override
  Future<KnowledgeVocabularyList?> listCategories({int page = 1, int pageSize = 20}) async => null;

  @override
  Future<KnowledgeVocabularyList?> listColors({int page = 1, int pageSize = 20}) async => null;

  @override
  Future<KnowledgeVocabularyList?> listOccasions({int page = 1, int pageSize = 20}) async => null;

  @override
  Future<KnowledgeItemReferenceList?> listItems({int page = 1, int pageSize = 20}) async => null;

  @override
  Future<FfoSchemaList?> listFfoSchemas({int page = 1, int pageSize = 20}) async => null;

  @override
  Future<Map<String, dynamic>?> getFfoSchema(String name) async => null;
}
