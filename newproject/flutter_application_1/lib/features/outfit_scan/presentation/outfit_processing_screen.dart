import 'dart:math';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class OutfitProcessingScreen extends StatefulWidget {
  const OutfitProcessingScreen({super.key, this.runId, this.client});

  final String? runId;
  final OutfitScanClient? client;

  @override
  State<OutfitProcessingScreen> createState() => _OutfitProcessingScreenState();
}

class _OutfitProcessingScreenState extends State<OutfitProcessingScreen> {
  static const _pollInterval = Duration(seconds: 3);
  static const _maxPollAttempts = 30;

  late final OutfitScanClient _client;
  String? _runId;
  Map<String, dynamic>? _runStatus;
  bool _isLoading = true;
  String? _errorMessage;
  Timer? _pollTimer;

  /// Poll clock for safe timing diagnostics (metadata only: run_id,
  /// HTTP status, state transitions, elapsed time — never image data).
  late final DateTime _pollStart;

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? OutfitScanClient();
    _runId = widget.runId;
    _pollStart = DateTime.now();
    // Phase 2: never poll a missing run id (guest-gated submits and
    // failed uploads both land here with null). The honest error + Back
    // to Scan below owns recovery — no request, no timer, no 401 storm.
    if (_runId == null || _runId!.isEmpty) {
      debugPrint('Outfit analysis polling aborted: missing run_id');
      _isLoading = false;
      _errorMessage = 'No run ID available';
      return;
    }
    debugPrint('Outfit analysis polling started: run_id=$_runId');
    _pollRunStatus();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _pollRunStatus({int attempts = 0}) async {
    if (!mounted) return;

    if (_runId == null || _runId!.isEmpty) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'No run ID available';
      });
      return;
    }

    if (attempts >= _maxPollAttempts) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Analysis polling timed out';
      });
      return;
    }

    try {
      final result = await _client.getAnalysisRun(_runId!);

      if (!mounted) return;

      if (result.statusCode == 200) {
        final data = result.data;
        setState(() {
          _runStatus = data;
          _isLoading = false;
        });

        if (result.isCompleted) {
          if (!mounted) return;
          debugPrint(
            'Outfit analysis polling completed: run_id=$_runId, '
            'elapsed_ms=${DateTime.now().difference(_pollStart).inMilliseconds}',
          );
          // The run envelope carries status metadata; the analysis UI
          // reads the `result` snapshot (appearance/confidence/
          // recommendations). Forward the snapshot, never the envelope.
          final snapshot = data?['result'] as Map<String, dynamic>?;
          context.pushNamed(
            RouteNames.scanAnalysis,
            extra: snapshot ?? data,
          );
          return;
        }

        if (result.isFailed) {
          if (!mounted) return;
          debugPrint(
            'Outfit analysis polling failed: run_id=$_runId, '
            'error=${result.error}, '
            'elapsed_ms=${DateTime.now().difference(_pollStart).inMilliseconds}',
          );
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                'Analysis failed: ${result.error ?? 'Unknown error'}',
              ),
              backgroundColor: FansivibeColors.error,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: FansivibeRadius.smdBorder,
              ),
            ),
          );
          // Stay inside the authenticated flow: the inline failed state
          // below (Back to Scan) owns recovery — never pop to entry.
          if (!mounted) return;
          setState(() {
            _isLoading = false;
          });
          return;
        }
      } else if (result.statusCode == 401) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Authentication error, please re-scan'),
            backgroundColor: FansivibeColors.error,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
        // True session expiry already routes to entry through
        // AuthSession; use the shell-safe GoRouter destination explicitly
        // instead of popping to the first route.
        if (!mounted) return;
        context.goNamed(RouteNames.entry);
        return;
      } else {
        // Truthful connection diagnostics (Phase 22, Step 8): status 0 is
        // offline/unreachable, 429 is rate-limited — never silent retry.
        // Past ~20 s (cold-model inference) say so instead of spinning
        // silently; still indeterminate, never a fake percentage.
        final elapsed = DateTime.now().difference(_pollStart);
        final message = result.statusCode == 0
            ? AppConfig.connectionHint
            : result.statusCode == 429
            ? 'Too many requests — please wait a moment and try again.'
            : elapsed > const Duration(seconds: 20)
            ? 'Still analyzing — this can take a little longer on the first scan.'
            : 'Server returned ${result.statusCode}, retrying...';
        setState(() {
          _errorMessage = message;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Polling error: $e';
        _isLoading = false;
      });
    }

    if (!mounted) return;
    final backoff = _pollInterval * (1 << min(attempts, 4));
    _pollTimer = Timer(backoff, () => _pollRunStatus(attempts: attempts + 1));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(_isLoading ? 'Analyzing Outfit' : 'Analysis Status'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 440.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                    ),
                    child: Column(
                      children: [
                        const SizedBox(height: 40),

                        if (_isLoading || _runStatus == null)
                          _buildProcessingIndicator()
                        else
                          _buildResultSummary(),

                        const SizedBox(height: 40),

                        if (_runStatus != null &&
                            _runStatus!['status'] != 'completed' &&
                            _runStatus!['status'] != 'failed')
                          Text(
                            _errorMessage ??
                                'Processing your outfit analysis...',
                            style: Theme.of(context).textTheme.bodyMedium
                                ?.copyWith(
                                  color: FansivibeColors.textSecondary,
                                ),
                            textAlign: TextAlign.center,
                          ),

                        const SizedBox(height: 40),

                        if (_runStatus != null &&
                            _runStatus!['status'] == 'completed')
                          FansiButton.primary(
                            label: 'View Results',
                            icon: Icons.check_circle_outline,
                            onPressed: () {
                              if (!mounted) return;
                              final snapshot =
                                  _runStatus?['result']
                                      as Map<String, dynamic>?;
                              context.pushNamed(
                                RouteNames.scanAnalysis,
                                extra: snapshot ?? _runStatus,
                              );
                            },
                          ),

                        if (_runStatus != null &&
                            _runStatus!['status'] == 'failed')
                          FansiButton.secondary(
                            label: 'Back to Scan',
                            icon: Icons.refresh_rounded,
                            onPressed: () {
                              if (!mounted) return;
                              context.pop();
                            },
                          ),

                        // Null run id (camera capture failed before upload):
                        // the spinner above never resolves, so surface the
                        // truthful error with a way back instead of a dead
                        // end. Happy-path polling is untouched.
                        if (_runId == null && !_isLoading) ...[
                          Text(
                            _errorMessage ?? 'No run ID available',
                            style: Theme.of(context).textTheme.bodyMedium
                                ?.copyWith(
                                  color: FansivibeColors.textSecondary,
                                ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 24),
                          FansiButton.secondary(
                            label: 'Back to Scan',
                            icon: Icons.refresh_rounded,
                            onPressed: () {
                              if (!mounted) return;
                              context.pop();
                            },
                          ),
                        ],

                        const SizedBox(height: 32),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildProcessingIndicator() {
    return Container(
      width: 160,
      height: 160,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: FansivibeColors.surface,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.3),
        ),
      ),
      child: Center(
        child: CircularProgressIndicator(
          strokeWidth: 4,
          valueColor: AlwaysStoppedAnimation<Color>(FansivibeColors.accentGold),
        ),
      ),
    );
  }

  Widget _buildResultSummary() {
    final status = _runStatus?['status'] ?? 'unknown';

    return Column(
      children: [
        Container(
          width: 160,
          height: 160,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: status == 'completed'
                ? FansivibeColors.success.withValues(alpha: 0.1)
                : FansivibeColors.error.withValues(alpha: 0.1),
            border: Border.all(
              color: status == 'completed'
                  ? FansivibeColors.success.withValues(alpha: 0.3)
                  : FansivibeColors.error.withValues(alpha: 0.3),
            ),
          ),
          child: status == 'completed'
              ? Icon(
                  Icons.check_circle_rounded,
                  size: 64,
                  color: FansivibeColors.success,
                )
              : Icon(
                  Icons.error_rounded,
                  size: 64,
                  color: FansivibeColors.error,
                ),
        ),
        const SizedBox(height: 24),
        Text(
          status == 'completed' ? 'Analysis Complete' : 'Analysis Failed',
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w600,
            color: status == 'completed'
                ? FansivibeColors.success
                : FansivibeColors.error,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _runStatus?['status'] == 'completed'
              ? 'Your outfit appearance has been analyzed'
              : 'We were unable to analyze your outfit. Please try again.',
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
