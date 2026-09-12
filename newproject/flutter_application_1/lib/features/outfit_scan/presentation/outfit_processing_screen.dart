import 'dart:math';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
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
  int _pollAttempts = 0;
  bool _isLoading = true;
  String? _errorMessage;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? OutfitScanClient();
    _runId = widget.runId;
    _pollRunStatus();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _pollRunStatus({int attempts = 0}) async {
    if (!mounted) return;

    if (_runId == null) {
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
          context.pushNamed(RouteNames.scanAnalysis, extra: data);
          return;
        }

        if (result.isFailed) {
          if (!mounted) return;
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
          if (!mounted) return;
          Navigator.of(context).popUntil((route) => route.isFirst);
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
        if (!mounted) return;
        Navigator.of(context).popUntil((route) => route.isFirst);
        return;
      } else {
        setState(() {
          _pollAttempts = attempts;
          _errorMessage = 'Server returned ${result.statusCode}, retrying...';
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
                              context.pushNamed(
                                RouteNames.scanAnalysis,
                                extra: _runStatus,
                              );
                            },
                          ),

                        if (_runStatus != null &&
                            _runStatus!['status'] == 'failed')
                          FansiButton.secondary(
                            label: 'Retry Scan',
                            icon: Icons.refresh_rounded,
                            onPressed: () {
                              if (!mounted) return;
                              context.pop();
                              context.goNamed('/home');
                            },
                          ),

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
