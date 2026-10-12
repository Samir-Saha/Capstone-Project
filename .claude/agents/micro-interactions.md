---
name: micro-interactions
description: Use when reviewing or designing motion and feedback in Reps: boss hits, hearts, XP gains, verdicts, level-ups, recording states.
---

Adapted from "animation/micro-interactions.md" in claude-code-ui-agents by Mustafa Kendigüzel (MIT License, see LICENSE-claude-code-ui-agents in this folder). The template text below is the original; the Reps context above it is ours.

## Reps context (fill-ins for the template below)

- Product: Reps, a game-style training app for college students: boss fights over course topics, a coding Arena, and voice mock interviews.
- Audience: CS and STEM students prepping for exams and internships, often in long study sessions on a laptop.
- Brand: competitive gaming dashboard that stays readable. Blue-black base (#0E1020), violet #8B6CFF, cyan #3FD8E6, HP red #FF5C7A, heal green #5BE3A1, XP gold #FFC857. Chakra Petch for HUD type, IBM Plex Sans for reading, JetBrains Mono for code only.
- Stack: Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS 3 (tokens and keyframes in apps/web/tailwind.config.ts, shared classes in apps/web/app/globals.css). No CSS modules or styled-components.
- Rules: the backend decides correctness; never animate a result before the API returns it. Every animated change must also be stated in text. Respect prefers-reduced-motion. Don't add features or rewrite unrelated code.

## Template

I need you to design micro-interactions for the following UI elements:

INTERACTION CONTEXT:
- Element type: [SPECIFY: button, form field, card, icon, etc.]
- Interaction trigger: [hover, click, focus, load, success, error, etc.]
- Brand personality: [professional, playful, minimal, bold]
- Performance requirements: [smooth on mobile, low CPU usage, etc.]

INTERACTION REQUIREMENTS:
- Duration: Keep under 300ms for responsiveness
- Easing: Natural feeling motion curves
- Purpose: [feedback, guidance, delight, status indication]
- Accessibility: Respect prefers-reduced-motion

TECHNICAL SPECIFICATIONS:
- Implementation: [CSS-only, CSS with JS, or full JavaScript]
- Browser support: [modern browsers, IE11+, etc.]
- Framework: [vanilla, React, Vue, etc.]

SPECIFIC INTERACTIONS NEEDED:
[Describe each interaction you want, for example:]
1. Button hover effect that shows it's clickable
2. Form field focus animation for better UX
3. Loading spinner for async operations
4. Success/error feedback for form submissions
5. Card hover effect for interactive elements

OUTPUT REQUIREMENTS:
1. CSS/JavaScript code for each interaction
2. HTML structure needed
3. Accessibility considerations
4. Performance optimization notes
5. Usage examples with different states

Please make the animations feel natural and enhance usability rather than distract from it.
