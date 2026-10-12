---
name: mobile-design-philosophy
description: Use for phone polish in Reps: navigation patterns, touch feedback timing, gestures, and mobile-specific interaction rules.
---

Adapted from "ui-design/mobile-design-philosophy.md" in claude-code-ui-agents by Mustafa Kendigüzel (MIT License, see LICENSE-claude-code-ui-agents in this folder). The template text below is the original; the Reps context above it is ours.

## Reps context (fill-ins for the template below)

- Product: Reps, a game-style training app for college students: boss fights over course topics, a coding Arena, and voice mock interviews.
- Audience: CS and STEM students prepping for exams and internships, often in long study sessions on a laptop.
- Brand: competitive gaming dashboard that stays readable. Blue-black base (#0E1020), violet #8B6CFF, cyan #3FD8E6, HP red #FF5C7A, heal green #5BE3A1, XP gold #FFC857. Chakra Petch for HUD type, IBM Plex Sans for reading, JetBrains Mono for code only.
- Stack: Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS 3 (tokens and keyframes in apps/web/tailwind.config.ts, shared classes in apps/web/app/globals.css). No CSS modules or styled-components.
- Rules: the backend decides correctness; never animate a result before the API returns it. Every animated change must also be stated in text. Respect prefers-reduced-motion. Don't add features or rewrite unrelated code.

## Template

I need you to create a mobile design system and implementation guide following Apple-level design aesthetics and modern mobile UX principles:

PROJECT CONTEXT:
- App type: [iOS app, Android app, PWA, responsive web]
- Industry: [specify industry context]
- Target audience: [demographics and technical proficiency]
- Brand personality: [professional, playful, premium, accessible]

DESIGN DECISION FRAMEWORK:
For every design element, address:
1. **Purpose**: Why does this element exist?
2. **Hierarchy**: How important is this in the information architecture?
3. **Context**: How does this relate to surrounding elements?
4. **Accessibility**: Can all users interact with this effectively?
5. **Performance**: Does this impact loading or interaction speed?

APPLE-LEVEL DESIGN AESTHETICS:
- Meticulous attention to detail in every element
- Intuitive user experience that feels natural
- Clean, sophisticated visual presentation
- Consistent spacing and alignment throughout
- Premium feel through thoughtful micro-interactions
- Pixel-perfect alignment and spacing
- Consistent interaction patterns across the entire app
- Subtle but meaningful feedback for every user action
- Emotional design that creates positive user feelings

MICRO-INTERACTION PRINCIPLES:
Define for each interaction:
- **Trigger**: What initiates the interaction?
- **Rules**: What happens during the interaction?
- **Feedback**: How does the user know something happened?
- **Loops**: Does the interaction repeat or evolve?
- **Modes**: How does the interaction change the app's state?

MOBILE-SPECIFIC REQUIREMENTS:

## Touch Interface Design:
- Minimum touch targets: 44x44px (iOS) / 48x48px (Android)
- Touch target spacing: Minimum 8px between interactive elements
- Thumb reach zones: Place primary actions in easy-reach areas
- Gesture conflicts: Avoid competing gestures (swipe vs scroll)
- Haptic feedback: Use sparingly for important confirmations
- Touch feedback: Visual response within 100ms of touch

## Mobile Navigation Patterns:
- **Tab Bar**: Maximum 5 tabs, use "More" for additional options
- **Bottom Sheets**: Modal content from bottom edge
- **Floating Action Button**: Primary action, bottom-right placement
- **Pull-to-Refresh**: Standard pattern for content updates
- **Swipe Actions**: Reveal secondary actions (delete, archive, share)

## Typography for Mobile:
- **Minimum Text Size**: 16px for body text (prevents zoom on iOS)
- **Line Height**: 1.4-1.6 for body text, 1.1-1.3 for headings
- **Measure**: 45-75 characters for optimal readability
- **Font Weight Hierarchy**: Maximum 3 weights for consistency
- **Reading Patterns**: F-pattern for content, Z-pattern for interfaces

## Mobile Color System:
Create comprehensive color system with:
- Primary color ramp (6-9 shades) with accessibility compliance
- Semantic colors (success, warning, error, info)
- Dark mode variations for all colors
- High contrast mode support
- Color independence (never rely solely on color for information)

## Performance Optimization:
- **Critical Rendering Path**: Inline critical CSS, defer non-critical
- **Image Optimization**: WebP format, responsive images, lazy loading
- **Animation Performance**: Use transform and opacity, avoid layout properties
- **60fps Animations**: Hardware acceleration with will-change property
- **Memory Management**: Cleanup event listeners, avoid memory leaks

## Accessibility Standards:
- **WCAG AA Compliance**: 4.5:1 contrast ratio minimum
- **Touch Accessibility**: Large enough targets, clear focus indicators
- **Screen Reader Support**: Semantic markup, ARIA labels
- **Motor Impairments**: No time limits, alternative input methods
- **Cognitive Load**: Simple language, clear instructions, error prevention

## Advanced Mobile Patterns:
- **Progressive Disclosure**: Primary → Secondary → Tertiary information hierarchy
- **Loading States**: Skeleton screens, progressive loading, optimistic updates
- **Error Recovery**: Clear error messages with actionable solutions
- **Form Design**: Single column, smart defaults, inline validation
- **Content Strategy**: Mobile-first content prioritization

OUTPUT REQUIREMENTS:
1. Complete mobile design system with color tokens and typography scale
2. Touch interface guidelines with interaction patterns
3. Component library optimized for mobile (buttons, forms, navigation)
4. Animation library with performance-optimized micro-interactions
5. Accessibility checklist and implementation guide
6. Performance optimization recommendations
7. Platform-specific considerations (iOS vs Android vs Web)
8. Testing methodology for mobile experiences

Please create a design system that feels as polished and intuitive as native iOS apps while being optimized for the specified platform and industry context.
