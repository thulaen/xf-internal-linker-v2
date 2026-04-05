# Scroll-and-Highlight Navigation System

A universal, reusable system for smooth scrolling and highlighting elements throughout the XF Internal Linker app.

## Quick Start

### 1. Simple Button Navigation (Easiest)

```html
<button appScrollHighlight="target-section-id">
  Jump to Section
</button>
```

The directive automatically:
- Prevents default click behavior
- Scrolls the page to center the target element
- Highlights it with a blue background + left border
- Holds the highlight for 6 seconds
- Gently fades it out

No component code required!

**Works on ANY element:**
- Buttons: `<button appScrollHighlight="id">`
- Links: `<a appScrollHighlight="id">`
- Menu items: `<mat-menu-item appScrollHighlight="id">`
- Sidebar items: `<a routerLink="/page" appScrollHighlight="id">`
- Divs: `<div appScrollHighlight="id" role="button">`
- Table rows, cards, list items... anything clickable

### 2. Material Buttons & Components

Works naturally with Angular Material buttons and any component:

```html
<!-- Material raised button -->
<button mat-raised-button color="primary" appScrollHighlight="important-section">
  Go to Important Section
</button>

<!-- Material icon button -->
<button mat-icon-button appScrollHighlight="help-docs" matTooltip="View Help">
  <mat-icon>help</mat-icon>
</button>

<!-- Material menu item -->
<mat-menu #menu="matMenu">
  <button mat-menu-item appScrollHighlight="error-logs">
    <mat-icon>error</mat-icon>
    <span>Show Errors</span>
  </button>
</mat-menu>
```

### 2b. Router Links (Cross-Page Navigation)

Scroll to sections on other pages:

```html
<!-- Navigate to page + scroll to section -->
<a routerLink="/system-health"
   appScrollHighlight="database-status"
   [scrollHighlightDelay]="200">
  Database Status
</a>

<!-- In sidebar -->
<a routerLink="/health"
   [routerLinkActive]="'active-link'"
   appScrollHighlight="cache-layer">
  Cache Status
</a>
```

**How it works:**
1. User clicks link
2. `routerLink` navigates to page
3. Route renders (200ms delay)
4. `appScrollHighlight` triggers scroll + highlight
5. User sees section centered with highlight animation

**Perfect for:**
- Sidebar navigation to page sections
- Menu links to specific features
- Alert system "View Details" links
- Breadcrumb navigation

### 3. Custom Options

Control highlight duration, fade timing, and more:

```html
<button
  appScrollHighlight="error-details"
  [scrollHighlightOptions]="{
    highlightDuration: 8000,  // 8 seconds instead of 6
    fadeDuration: 600          // 600ms fade instead of 500ms
  }">
  Show Errors
</button>
```

### 4. Listen for Completion

Get notified when the animation finishes:

```html
<button
  appScrollHighlight="results"
  (scrollComplete)="onScrollFinished()">
  View Results
</button>
```

```typescript
onScrollFinished(): void {
  console.log('Scroll and highlight animation complete');
}
```

### 5. Programmatic Service Usage

Call the service directly in component code:

```typescript
import { inject } from '@angular/core';
import { ScrollHighlightService } from './core/services/scroll-highlight.service';

export class MyComponent {
  private scrollHighlight = inject(ScrollHighlightService);

  onSearchResultClick(resultId: string): void {
    // Scroll to and highlight the result
    this.scrollHighlight.scrollToAndHighlight(`#result-${resultId}`, {
      highlightDuration: 4000,  // Shorter hold for search results
    });
  }

  cancelHighlight(): void {
    // Cancel the current highlight animation
    this.scrollHighlight.cancelHighlight();
  }
}
```

### 6. Alert Navigation

In alert/toast components that need to navigate to content:

```typescript
onAlertAction(alert: OperatorAlert): void {
  const scrollSvc = inject(ScrollHighlightService);

  if (alert.related_route.includes('#')) {
    const [path, id] = alert.related_route.split('#');
    this.router.navigateByUrl(path).then(() => {
      // Wait for route to render, then scroll
      scrollSvc.scrollToAndHighlight(`#${id}`);
    });
  } else {
    this.router.navigateByUrl(alert.related_route);
  }
}
```

### 7. Deep Links with Hash Fragments

Users can deep-link to sections within pages, and they automatically scroll + highlight:

```
https://yourapp.com/page#section-id
```

The app automatically detects the hash fragment and triggers `scrollToAndHighlight()`.

## How It Works

### The Animation Timeline

```
0ms          → User clicks button
0-350ms      → Page smoothly scrolls to center element
350ms        → Blue highlight appears (primary color @ 12% opacity)
350-5500ms   → Highlight holds (6000ms total duration)
5500-6000ms  → Highlight gently fades to transparent
6000ms+      → Animation complete, classes removed
```

### Visual Style

**Applied class**: `.scroll-highlight`
- Background: `rgba(26, 115, 232, 0.12)` (GA4 blue @ 12%)
- Left border: `2px solid var(--color-primary)`
- Inset shadow for depth

**Fade class**: `.scroll-highlight--fade`
- Transparent background
- Transparent border
- CSS transition handles smooth fade (500ms, ease-out)

## Configuration Options

All options are optional; sensible defaults are provided.

### ScrollHighlightOptions Interface

```typescript
interface ScrollHighlightOptions {
  /** Scroll animation: 'smooth' or 'auto'. Default: 'smooth' */
  scrollBehavior?: 'smooth' | 'auto';

  /** Duration to hold highlight (ms). Default: 6000 */
  highlightDuration?: number;

  /** Duration of fade-out animation (ms). Default: 500 */
  fadeDuration?: number;

  /** CSS class for highlight. Default: 'scroll-highlight' */
  highlightClass?: string;

  /** Duration of manual scroll (ms). Default: 350. Only for scrollBehavior='auto' */
  scrollDuration?: number;

  /** Container to scroll. Default: window */
  scrollContainer?: HTMLElement | Window;

  /** Callback when animation completes */
  onComplete?: () => void;
}
```

### Directive-Specific Options

When using the directive, two additional options are available:

```html
<!-- scrollHighlightDelay: Wait before triggering scroll-highlight (useful with routerLink) -->
<a routerLink="/page"
   appScrollHighlight="section"
   [scrollHighlightDelay]="150">
  Navigate and Scroll
</a>

<!-- scrollHighlightOptions: Pass all ScrollHighlightOptions shown above -->
<button appScrollHighlight="critical-error"
        [scrollHighlightOptions]="{
          highlightDuration: 10000,
          fadeDuration: 800,
          onComplete: () => playSound()
        }">
  Show Critical Error
</button>
```

**Default Delays:**
- Standalone element (button, link): 0ms (immediate)
- With `routerLink`: 100ms (allows route to render)
- Custom delay: Set `[scrollHighlightDelay]="ms"`

**Recommended Delays:**
- Same page scroll: 0ms (immediate)
- Cross-page navigation: 100-200ms (route + component init)
- Complex page with animations: 300ms

## Selector Formats

Both formats work (with or without `#` prefix):

```html
<button appScrollHighlight="my-section">✓ Works</button>
<button appScrollHighlight="#my-section">✓ Also works</button>
```

## Edge Cases & Error Handling

| Scenario | Behavior |
|----------|----------|
| **Element doesn't exist** | Clear error logged to console; app doesn't crash |
| **Element is hidden** | Scroll happens but highlight may not be visible; warning logged |
| **User scrolls manually** | Highlight is not interrupted; user retains page control |
| **Multiple rapid clicks** | Previous highlight cancels immediately; new one begins |
| **Element at page bottom** | Scrolls naturally to available space; may land near bottom |
| **Mobile viewport** | Center calculation adapts automatically to viewport height |

## Real-World Examples (From This App)

### Health Page: Jump to Status Section

```html
<!-- In health.component.html -->
<div class="quick-links">
  <button mat-raised-button appScrollHighlight="database-status">
    Database Status
  </button>
  <button mat-raised-button appScrollHighlight="services-status">
    Services Status
  </button>
  <button mat-raised-button appScrollHighlight="cache-status">
    Cache Status
  </button>
</div>

<!-- Corresponding sections below -->
<mat-card id="database-status">
  <mat-card-header><h2>Database Status</h2></mat-card-header>
  <mat-card-content><!-- DB details --></mat-card-content>
</mat-card>
```

### Alert System: View Details Link

```typescript
// In alert-delivery.service.ts or toast component
onAlertViewDetails(alert: OperatorAlert): void {
  const router = inject(Router);
  const scrollHighlight = inject(ScrollHighlightService);

  // If alert has a section on the same page
  if (alert.related_route === '#webhook-logs') {
    scrollHighlight.scrollToAndHighlight(alert.related_route);
  } else if (alert.related_route === '/health#database') {
    // Navigate to health page, then scroll
    router.navigateByUrl('/health').then(() => {
      setTimeout(() => scrollHighlight.scrollToAndHighlight('#database'), 100);
    });
  }
}
```

```html
<!-- In alert toast/card -->
<button mat-button (click)="onAlertViewDetails(alert)" *ngIf="alert.related_route">
  View Details →
</button>
```

### Sidebar: Deep Link to Page Sections

```html
<!-- In app.component.html (future enhancement) -->
<mat-nav-list class="app-sidenav-list">
  <mat-list-item>
    <a matListItemTitle
       routerLink="/health"
       routerLinkActive="active-link"
       appScrollHighlight="database-status">
      Database Health
    </a>
  </mat-list-item>

  <mat-list-item>
    <a matListItemTitle
       routerLink="/system-health"
       appScrollHighlight="cache-layer">
      Cache Status
    </a>
  </mat-list-item>
</mat-nav-list>
```

### Table Row: Jump to Details

```html
<!-- In review.component.html -->
<mat-table [dataSource]="suggestions$ | async">
  <!-- Table columns... -->

  <ng-container matColumnDef="actions">
    <td mat-cell *matCellDef="let suggestion">
      <button mat-icon-button
              appScrollHighlight="suggestion-{{ suggestion.id }}"
              matTooltip="View Details">
        <mat-icon>open_in_new</mat-icon>
      </button>
    </td>
  </ng-container>
</mat-table>

<!-- Details section -->
<div *ngFor="let suggestion of (suggestions$ | async)"
     [id]="'suggestion-' + suggestion.id"
     class="detail-card">
  <mat-card>
    <mat-card-header>{{ suggestion.title }}</mat-card-header>
    <mat-card-content>{{ suggestion.details }}</mat-card-content>
  </mat-card>
</div>
```

### Dashboard Quick Links

```html
<!-- In dashboard.component.html -->
<div class="dashboard-shortcuts">
  <mat-card class="shortcut" appScrollHighlight="recent-jobs">
    <h3>Recent Jobs</h3>
    <p>{{ jobCount }} running</p>
  </mat-card>

  <mat-card class="shortcut" appScrollHighlight="failed-links">
    <h3>Failed Links</h3>
    <p>{{ failureCount }} found</p>
  </mat-card>
</div>

<mat-card id="recent-jobs">
  <mat-card-header><h2>Recent Jobs</h2></mat-card-header>
  <mat-card-content><!-- Jobs list --></mat-card-content>
</mat-card>

<mat-card id="failed-links">
  <mat-card-header><h2>Failed Links</h2></mat-card-header>
  <mat-card-content><!-- Links list --></mat-card-content>
</mat-card>
```

---

For more comprehensive integration patterns, see **SCROLL_HIGHLIGHT_INTEGRATION.md**.

## Files & Structure

- **Service**: `frontend/src/app/core/services/scroll-highlight.service.ts`
- **Directive**: `frontend/src/app/core/directives/scroll-highlight.directive.ts`
- **Utilities**: `frontend/src/app/core/utils/scroll-highlight.utils.ts`
- **Styles**: `frontend/src/styles/_scroll-highlight.scss`

**Documentation:**
- **SCROLL_HIGHLIGHT_USAGE.md** — Quick start and API reference
- **SCROLL_HIGHLIGHT_INTEGRATION.md** — Real-world patterns for every component type

## Testing

### Manual Testing Steps

1. Add buttons with `appScrollHighlight` directive to any page:
   ```html
   <button appScrollHighlight="section-1">Go to Section 1</button>
   <button appScrollHighlight="section-2">Go to Section 2</button>

   <div id="section-1">
     <h2>Section 1</h2>
     <p>Content here...</p>
   </div>

   <div id="section-2">
     <h2>Section 2</h2>
     <p>More content...</p>
   </div>
   ```

2. Click each button and verify:
   - ✓ Page smoothly scrolls
   - ✓ Section centers in viewport
   - ✓ Blue highlight appears
   - ✓ Highlight holds for ~6 seconds
   - ✓ Highlight fades smoothly
   - ✓ Classes are removed after fade

3. Test rapid clicks:
   - Click button A
   - Click button B within 1-2 seconds
   - ✓ A's highlight cancels immediately
   - ✓ B starts fresh animation

4. Test mobile:
   - Resize viewport to mobile width (375px)
   - ✓ Scroll and highlight still works
   - ✓ Element centers correctly

## API Reference

### ScrollHighlightService

```typescript
@Injectable({ providedIn: 'root' })
export class ScrollHighlightService {
  /**
   * Scroll to element and apply highlight animation.
   * @param selector CSS selector of target element
   * @param options Configuration options (optional)
   */
  scrollToAndHighlight(selector: string, options?: ScrollHighlightOptions): void

  /**
   * Cancel the current highlight animation immediately.
   */
  cancelHighlight(): void
}
```

### ScrollHighlightDirective

```typescript
@Directive({ selector: '[appScrollHighlight]', standalone: true })
export class ScrollHighlightDirective {
  @Input() appScrollHighlight: string;                    // Element ID
  @Input() scrollHighlightOptions?: ScrollHighlightOptions;
  @Output() scrollComplete = new EventEmitter<void>();
}
```

### Utility Functions

```typescript
// Calculate scroll offset to center element in viewport
export function calculateCenterScroll(
  element: HTMLElement,
  scrollContainer?: HTMLElement | Window
): number

// Check if element is visible in viewport
export function isElementVisible(element: HTMLElement, threshold?: number): boolean

// Validate selector and return element (throws if not found)
export function validateAndGetElement(selector: string): HTMLElement
```

## Performance Notes

- ✓ No memory leaks: RxJS subscriptions properly cleaned up
- ✓ Efficient DOM: Single class toggle, CSS handles animation
- ✓ No layout thrashing: Scroll calculated once, applied in batch
- ✓ GPU accelerated: CSS transitions handle fade animation
- ✓ Lightweight directives: Minimal overhead per element

## Design Principles

1. **Universal**: Works on any clickable element (buttons, links, custom)
2. **Reusable**: One-line template syntax or service injection
3. **Accessible**: Scrolling visible, no hidden content
4. **Responsive**: Adapts to any viewport size
5. **Professional**: Feels like a modern, polished web app
6. **GA4 Aligned**: Uses primary color and flat design consistent with app

## Future Enhancements

- Custom highlight colors for different contexts (error, success, warning)
- Support for custom scroll containers (multi-pane layouts)
- Keyboard navigation (Ctrl+G to "Go to" dialog)
- Search results highlighting
- Smart scroll offset for fixed headers

---

**Questions?** Check the service TypeDoc comments or refer to the implementation files.
