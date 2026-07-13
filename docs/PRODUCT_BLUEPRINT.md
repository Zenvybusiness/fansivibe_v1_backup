# Fansivibe Product Blueprint

## Product Goal

Fansivibe is a personalized AI style intelligence platform.

It combines user style context, wardrobe data, images, preferences, and
events to provide practical style recommendations.

## Core Systems

### Home

Purpose:
Daily personalized style dashboard.

Main content:

- Today's Look
- Style Score
- Style Streak
- AI Insight
- Quick Outfit Scan

Daily recommendations may use:

- Style DNA
- wardrobe
- events
- weather
- preferences
- previous choices

### Discover

Purpose:
Personalized style discovery.

Supports:

- For You
- Trending
- Search
- Filters
- Match Score
- Look Details
- Wardrobe Alternatives

Look details should explain why a recommendation matches the user.

### Stylist

Purpose:
Launch specialized AI workflows.

Actions:

- Scan My Outfit
- Build Outfit From Wardrobe
- Hairstyle Recommendation
- Beard / Glasses Suggestion
- Event Planning

Stylist is not primarily a chatbot.

### Outfit Scan

Flow:

Capture Image
→ Validate Capture
→ Process
→ Analyze
→ Show Result

Possible analysis:

- silhouette
- proportions
- balance
- fit
- volume
- color harmony
- structure
- detected clothing

Analysis sections must be structured and expandable.

### Wardrobe

Purpose:
Digital wardrobe and AI context.

Supports:

- view items
- filter items
- add items
- categorize clothing
- wardrobe insights

Wardrobe categories must be data-driven.

Possible item data:

- category
- type
- colors
- material
- texture
- fit
- style tags
- occasion tags
- season tags

### Outfit Builder

Current inputs:

- occasion
- mood
- preferred fit
- color palette

The system combines preferences with wardrobe and Style DNA.

Result may include:

- match score
- outfit components
- reasons
- fit metrics
- Style Score impact
- improvements
- component alternatives

Inputs and outfit component slots must be expandable.

### Hairstyle

Flow:

Face Scan
→ Validate Image
→ Analyze Style Attributes
→ Rank Hairstyles
→ Show Recommendations

Recommendation context may include:

- face shape
- skin tone
- Style DNA

Results include reasons and alternatives.

### Grooming

Supports beard and eyewear recommendations.

Current context may include:

- face shape
- beard style
- beard density
- beard color

Results may include:

- match score
- reasons
- grooming specifications
- alternatives

### Events

Events provide context for outfit recommendations.

Current event data:

- name
- date
- time
- event type

Future event context may include dress code, location, and calendar
integration.

### Profile / Style Identity

Represents the user's evolving style profile.

May include:

- Style Score
- progress
- achievements
- saved looks
- Style DNA
- skin tone
- face shape
- body type
- style type

## Expansion Rule

Fansivibe will gain new features.

Potential future features:

- Skincare AI
- Accessories AI
- Hair Care AI
- Fragrance AI
- Packing Assistant
- Virtual Try-On

New features should be independently addable.

Prefer structured, configuration-driven product systems over hardcoded
feature logic.