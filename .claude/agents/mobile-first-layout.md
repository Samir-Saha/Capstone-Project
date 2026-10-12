---
name: mobile-first-layout
description: Use when adapting Reps screens to phones and tablets: breakpoints, touch targets, thumb reach, layout stacking.
---

Adapted from "responsive/mobile-first-layout.md" in claude-code-ui-agents by Mustafa Kendigüzel (MIT License, see LICENSE-claude-code-ui-agents in this folder). The template text below is the original; the Reps context above it is ours.

## Reps context (fill-ins for the template below)

- Product: Reps, a game-style training app for college students: boss fights over course topics, a coding Arena, and voice mock interviews.
- Audience: CS and STEM students prepping for exams and internships, often in long study sessions on a laptop.
- Brand: competitive gaming dashboard that stays readable. Blue-black base (#0E1020), violet #8B6CFF, cyan #3FD8E6, HP red #FF5C7A, heal green #5BE3A1, XP gold #FFC857. Chakra Petch for HUD type, IBM Plex Sans for reading, JetBrains Mono for code only.
- Stack: Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS 3 (tokens and keyframes in apps/web/tailwind.config.ts, shared classes in apps/web/app/globals.css). No CSS modules or styled-components.
- Rules: the backend decides correctness; never animate a result before the API returns it. Every animated change must also be stated in text. Respect prefers-reduced-motion. Don't add features or rewrite unrelated code.

## Template

I need you to create a mobile-first responsive layout with the following specifications:

LAYOUT REQUIREMENTS:
- Layout type: [landing page, dashboard, blog, e-commerce, portfolio]
- Sections needed: [header, hero, features, testimonials, footer, etc.]
- Content priority: [which content is most important on mobile]

BREAKPOINT STRATEGY:
- Mobile: 320px - 768px (primary focus)
- Tablet: 768px - 1024px
- Desktop: 1024px+
- Large screens: 1400px+ (optional)

DESIGN SPECIFICATIONS:
- Typography: Responsive type scaling
- Images: Responsive images with proper sizing
- Navigation: Mobile-friendly menu system
- Touch targets: Minimum 44px for interactive elements
- Performance: Optimize for mobile loading speeds

TECHNICAL REQUIREMENTS:
- CSS methodology: [BEM, CSS modules, styled-components, etc.]
- CSS features: Use modern Grid/Flexbox
- Framework: [vanilla CSS, Tailwind, Bootstrap, etc.]
- Browser support: [specify minimum requirements]

SPECIFIC LAYOUT DETAILS:
[Describe your specific layout needs, for example:]
- Header with logo and hamburger menu on mobile
- Hero section with background image and call-to-action
- Three-column feature section that stacks on mobile
- Responsive card grid that adapts to screen size
- Footer with collapsible sections on mobile

OUTPUT REQUIREMENTS:
1. HTML structure with semantic elements
2. Mobile-first CSS with progressive enhancement
3. Breakpoint documentation
4. Performance optimization notes
5. Cross-browser testing checklist

Please prioritize mobile user experience while ensuring desktop doesn't feel like an afterthought.
