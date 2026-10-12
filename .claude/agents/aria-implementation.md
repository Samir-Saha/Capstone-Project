---
name: aria-implementation
description: Use when checking Reps for keyboard and screen-reader access: live HP and score updates, the code editor, mic controls, dialogs and tabs.
---

Adapted from "accessibility/aria-implementation.md" in claude-code-ui-agents by Mustafa Kendigüzel (MIT License, see LICENSE-claude-code-ui-agents in this folder). The template text below is the original; the Reps context above it is ours.

## Reps context (fill-ins for the template below)

- Product: Reps, a game-style training app for college students: boss fights over course topics, a coding Arena, and voice mock interviews.
- Audience: CS and STEM students prepping for exams and internships, often in long study sessions on a laptop.
- Brand: competitive gaming dashboard that stays readable. Blue-black base (#0E1020), violet #8B6CFF, cyan #3FD8E6, HP red #FF5C7A, heal green #5BE3A1, XP gold #FFC857. Chakra Petch for HUD type, IBM Plex Sans for reading, JetBrains Mono for code only.
- Stack: Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS 3 (tokens and keyframes in apps/web/tailwind.config.ts, shared classes in apps/web/app/globals.css). No CSS modules or styled-components.
- Rules: the backend decides correctness; never animate a result before the API returns it. Every animated change must also be stated in text. Respect prefers-reduced-motion. Don't add features or rewrite unrelated code.

## Template

I need you to help me implement proper ARIA attributes and accessibility features for the following component:

COMPONENT DETAILS:
- Component type: [dropdown, modal, tabs, carousel, form, etc.]
- Current implementation: [describe existing HTML/React/Vue structure]
- Framework: [vanilla HTML, React, Vue, Angular]
- WCAG level target: [AA or AAA compliance]

ACCESSIBILITY REQUIREMENTS:

1. SCREEN READER SUPPORT:
- Proper labeling and descriptions
- Announce state changes
- Navigation instructions
- Content structure clarity

2. KEYBOARD NAVIGATION:
- Tab order and focus management
- Keyboard shortcuts (if applicable)
- Escape key handling
- Arrow key navigation (for complex components)

3. ARIA ATTRIBUTES NEEDED:
- Role definitions
- Properties (aria-labelledby, aria-describedby, etc.)
- States (aria-expanded, aria-selected, etc.)
- Live regions for dynamic content

4. VISUAL INDICATORS:
- Focus indicators
- High contrast support
- Reduced motion compliance

SPECIFIC CHALLENGES:
[Describe any specific accessibility challenges with your component]

OUTPUT REQUIREMENTS:
1. Updated HTML with proper ARIA attributes
2. JavaScript for managing dynamic ARIA states
3. CSS for visual accessibility features
4. Testing checklist with screen reader instructions
5. Documentation explaining the accessibility features

Please ensure the implementation follows WCAG 2.1 guidelines and works well with popular screen readers (NVDA, JAWS, VoiceOver).
