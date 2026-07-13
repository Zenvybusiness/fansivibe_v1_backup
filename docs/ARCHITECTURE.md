# Fansivibe Architecture

## Goal

Fansivibe must support safe incremental feature expansion.

## Architecture

Use feature-first modular architecture.

lib/
├── app/
├── core/
├── shared/
└── features/

## Responsibilities

### app/

Application composition:

- bootstrap
- router
- navigation shell

### core/

Application infrastructure:

- network
- storage
- environment
- errors
- logging
- permissions
- feature flags

Do not place product screens in `core/`.

### shared/

Actually reusable UI and simple shared concepts.

Do not place feature-specific business logic in `shared/`.

### features/

Major product capabilities.

Examples:

features/
├── auth/
├── home/
├── discover/
├── stylist/
├── wardrobe/
├── outfit_scan/
├── outfit_builder/
├── hairstyle/
├── grooming/
├── events/
├── style_profile/
└── profile/

## Feature Structure

Use only layers required by actual complexity.

A substantial feature may use:

feature/
├── README.md
├── data/
├── domain/
└── presentation/

Do not create empty layers only to imitate Clean Architecture.

## Dependency Rule

Presentation must not call APIs directly.

Preferred flow:

UI
→ Controller / State
→ Use Case
→ Repository Contract
→ Repository Implementation
→ Data Source

## Feature Isolation

Features own their internal implementation.

A feature must not import another feature's internal:

- data sources
- repository implementations
- controllers
- presentation state

Use an intentional public contract for cross-feature communication.

## State Management

Use the project's approved state-management approach.

Do not introduce or mix another state-management library without approval.

Keep state at the narrowest appropriate scope.

## Navigation

Primary tabs:

Home
Discover
Stylist
Wardrobe
Profile

Use the existing approved routing approach.

Do not scatter raw route strings throughout UI code.

## AI

Flutter
→ Fansivibe Backend
→ AI Orchestrator
→ AI Provider

Flutter must not depend on Gemini, OpenAI, Claude, or another provider
directly.

AI responses must use typed structured schemas.

The AI must not control widget structure or navigation.

## Expandable Data

Prefer configuration-driven models for:

- wardrobe categories
- Discover filters
- stylist actions
- event types
- analysis sections
- recommendation reasons
- outfit component slots

Avoid large hardcoded conditional chains.

## Feature Flags

Optional features should support feature flags when the infrastructure is
introduced.

Feature flags may support rollout, beta access, premium access, country
availability, and emergency disabling.

## Architecture Changes

Do not migrate architecture, routing, state management, or networking as
part of normal feature work.

Major changes require approval and a `DECISIONS.md` entry.