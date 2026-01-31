# TypeScript/React Code Rules

## Components
- Use functional components with hooks (no class components)
- Use `interface` for component props
- Export components as named exports, not default
- Co-locate component, types, and styles in same directory when complex

## Typing
- Enable strict mode in tsconfig
- Use `interface` for object shapes that may be extended
- Use `type` for unions, intersections, and mapped types
- Avoid `any` - use `unknown` and narrow with type guards

## State Management
- Use React Context for global state (AnalysisContext pattern)
- Use `useReducer` for complex state with many updates
- Avoid prop drilling beyond 2 levels - use Context
- Memoize expensive computations with `useMemo`

## Tailwind CSS
- Use Tailwind classes, not inline styles or CSS modules
- Extract repeated patterns to components, not @apply
- Use design tokens from tailwind config
- Keep class lists readable (line breaks OK)

## Charts (lightweight-charts)
- Import dynamically: `dynamic(() => import(...), { ssr: false })`
- Clean up chart instances in useEffect return
- Use refs for chart/series instances
- Sync multiple charts via time scale subscriptions

## API Calls
- Use fetch with proper error handling
- Type API responses with interfaces
- Handle loading and error states in components
- Use SSE for streaming (streamChat pattern)
