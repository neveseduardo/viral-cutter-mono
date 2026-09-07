---
name: chrome-devtools
description: Browser automation and debugging with Chrome DevTools MCP. Use for E2E testing, inspecting pages, console errors, network requests, DOM state, and screenshots.
---

# Chrome DevTools

Use the `chrome-devtools` MCP for browser-based testing and debugging.

## General rules

- Use the browser for E2E validation when appropriate.
- Prefer `take_snapshot` to understand page structure and locate elements.
- Use the `uid` returned by snapshots for interactions.
- Take a new snapshot after navigation or significant DOM changes.
- Use screenshots only when visual verification is necessary.
- Avoid dumping large amounts of browser data into the context.
- Prefer targeted inspection over broad inspection.

## E2E workflow

1. List pages only when the current page is unknown.
2. Navigate to the target URL.
3. Wait for the relevant page state.
4. Take a snapshot.
5. Interact with the required elements.
6. Verify the resulting state.
7. Inspect console/network only when the test fails or debugging requires it.

## Debugging

When an E2E operation fails:

1. Check console messages.
2. Check relevant network requests.
3. Inspect the DOM with a targeted snapshot.
4. Use `evaluate_script` only when direct inspection is insufficient.

Do not automatically collect console logs, network requests, screenshots, or performance traces unless they are relevant to the task.

## Output discipline

Keep browser tool usage targeted.

Do not repeatedly call `list_pages`, `take_snapshot`, screenshots, console inspection, or network inspection without a reason.

When a tool returns a large result, extract only the information required for the current task and avoid unnecessarily reproducing the entire result in subsequent responses.

## Performance

Only use performance tracing when the user explicitly requests performance analysis or when diagnosing a performance-related problem.