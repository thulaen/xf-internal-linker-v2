import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { NavigationCoordinatorService } from '../../services/navigation-coordinator.service';
import { COMMANDS, Command } from '../../services/command-palette.commands';

/**
 * App-wide Command Palette.
 *
 * Opens on Ctrl+K / Cmd+K from the app shell. Search-as-you-type across label,
 * description, and keywords. Arrow Up/Down changes selection, Enter executes
 * the selected command. Escape closes (handled by mat-dialog by default).
 *
 * Each command delegates navigation to NavigationCoordinatorService so the
 * route, fragment, and 6-second scroll-highlight arrival ring are identical
 * to the rest of the app's deep-linking behaviour.
 */
@Component({
  selector: 'app-command-palette',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
    MatListModule,
  ],
  template: `
    <div class="palette-wrap" role="dialog" aria-label="Command palette">
      <div class="palette-search">
        <mat-icon class="search-icon" aria-hidden="true">search</mat-icon>
        <input
          #searchInput
          class="search-input"
          type="text"
          placeholder="Type a command, page name, or keyword (e.g. 'perf', 'jobs', 'health')"
          aria-label="Command palette search"
          [ngModel]="query()"
          (ngModelChange)="onQueryChange($event)"
          autocomplete="off"
          autocorrect="off"
          spellcheck="false"
        />
      </div>

      @if (filtered().length === 0) {
        <div class="palette-empty">
          <mat-icon aria-hidden="true">search_off</mat-icon>
          <span>No commands match "{{ query() }}"</span>
        </div>
      } @else {
        @for (group of grouped(); track group.section) {
          <div class="palette-group-label">{{ group.section }}</div>
          <mat-nav-list class="palette-list" role="listbox">
            @for (cmd of group.commands; track cmd.id) {
              <a
                mat-list-item
                class="palette-item"
                [class.palette-item-selected]="isSelected(cmd)"
                (click)="execute(cmd)"
                (mouseenter)="onHover(cmd)"
                role="option"
                [attr.aria-selected]="isSelected(cmd)"
              >
                <mat-icon matListItemIcon class="palette-item-icon">{{ cmd.icon }}</mat-icon>
                <div matListItemTitle class="palette-item-title">{{ cmd.label }}</div>
                <div matListItemLine class="palette-item-desc">{{ cmd.description }}</div>
                @if (isSelected(cmd)) {
                  <span matListItemMeta class="palette-item-enter" aria-hidden="true">&#x21B5;</span>
                }
              </a>
            }
          </mat-nav-list>
        }
      }

      <footer class="palette-footer" aria-hidden="true">
        <span class="palette-kbd-group">
          <kbd class="palette-kbd">&#x2191;</kbd><kbd class="palette-kbd">&#x2193;</kbd>
          <span class="palette-kbd-label">to navigate</span>
        </span>
        <span class="palette-kbd-group">
          <kbd class="palette-kbd">&#x21B5;</kbd>
          <span class="palette-kbd-label">to select</span>
        </span>
        <span class="palette-kbd-group">
          <kbd class="palette-kbd">Esc</kbd>
          <span class="palette-kbd-label">to close</span>
        </span>
      </footer>
    </div>
  `,
  styles: [`
    .palette-wrap {
      display: flex;
      flex-direction: column;
      max-height: 70vh;
      min-height: 240px;
      background: var(--color-bg-white);
    }
    .palette-search {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-md);
      border-bottom: var(--card-border);
    }
    .search-icon {
      color: var(--color-text-muted);
      font-size: 20px;
      width: 20px;
      height: 20px;
    }
    .search-input {
      flex: 1;
      border: 0;
      outline: 0;
      background: transparent;
      font-family: inherit;
      font-size: 15px;
      color: var(--color-text-primary);
    }
    .search-input::placeholder {
      color: var(--color-text-muted);
    }
    .palette-empty {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-lg);
      color: var(--color-text-muted);
      font-size: 13px;
    }
    .palette-group-label {
      padding: var(--space-md) var(--space-md) var(--space-xs);
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--color-text-muted);
    }
    .palette-list {
      padding: 0;
    }
    .palette-item {
      transition: background 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .palette-item-selected {
      background: var(--color-blue-50);
    }
    .palette-item-icon {
      color: var(--color-text-secondary);
    }
    .palette-item-title {
      font-size: 13px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .palette-item-desc {
      font-size: 12px;
      color: var(--color-text-muted);
    }
    .palette-item-enter {
      font-size: 13px;
      color: var(--color-primary);
    }
    .palette-footer {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-md);
      padding: var(--space-sm) var(--space-md);
      border-top: var(--card-border);
      background: var(--color-bg-faint);
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .palette-kbd-group {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
    }
    .palette-kbd {
      display: inline-block;
      min-width: 20px;
      padding: 2px 6px;
      border: var(--card-border);
      border-radius: var(--radius-sm);
      background: var(--color-bg-white);
      font-family: inherit;
      font-size: 11px;
      text-align: center;
      color: var(--color-text-secondary);
    }
  `],
})
export class CommandPaletteComponent implements AfterViewInit {
  private dialogRef = inject(MatDialogRef<CommandPaletteComponent>);
  private nav = inject(NavigationCoordinatorService);

  @ViewChild('searchInput') searchInputEl!: ElementRef<HTMLInputElement>;

  /** Current search text. */
  query = signal('');
  /** Currently highlighted command id. Moves with arrow keys + hover. */
  selectedId = signal<string>(COMMANDS[0]?.id ?? '');

  /**
   * Commands matching the current query, preserving source order.
   *
   * Multi-word queries are AND-matched across the full haystack (label +
   * description + keywords). So typing "perf mode" finds "Change Performance
   * Mode" even though those words appear in different fields.
   */
  filtered = computed<Command[]>(() => {
    const q = this.query().trim().toLowerCase();
    if (!q) return COMMANDS;
    const tokens = q.split(/\s+/).filter(Boolean);
    return COMMANDS.filter((c) => {
      const haystack = [c.label, c.description, ...(c.keywords ?? [])]
        .join(' ')
        .toLowerCase();
      return tokens.every((t) => haystack.includes(t));
    });
  });

  /** Filtered commands grouped by section for rendering. */
  grouped = computed<{ section: string; commands: Command[] }[]>(() => {
    const groups = new Map<string, Command[]>();
    for (const cmd of this.filtered()) {
      const bucket = groups.get(cmd.section);
      if (bucket) {
        bucket.push(cmd);
      } else {
        groups.set(cmd.section, [cmd]);
      }
    }
    return Array.from(groups.entries()).map(([section, commands]) => ({
      section,
      commands,
    }));
  });

  ngAfterViewInit(): void {
    // Guarantee focus lands in the search input immediately. autoFocus in the
    // dialog config does this already, but a queued microtask is a safe belt.
    queueMicrotask(() => this.searchInputEl?.nativeElement.focus());
  }

  onQueryChange(q: string): void {
    this.query.set(q);
    // Reset the highlight to the first filtered result so Enter feels natural.
    const first = this.filtered()[0];
    this.selectedId.set(first?.id ?? '');
  }

  onHover(cmd: Command): void {
    this.selectedId.set(cmd.id);
  }

  isSelected(cmd: Command): boolean {
    return this.selectedId() === cmd.id;
  }

  execute(cmd: Command): void {
    this.nav.navigateTo(cmd.target);
    this.dialogRef.close();
  }

  /**
   * Keyboard navigation inside the palette.
   *  - Arrow Up/Down move the highlight (Ctrl+P/N also supported, terminal-style)
   *  - Enter executes the highlighted command
   *  - Escape is handled by mat-dialog automatically
   */
  @HostListener('document:keydown', ['$event'])
  onKeydown(event: KeyboardEvent): void {
    const list = this.filtered();
    if (list.length === 0) return;

    if (event.key === 'ArrowDown' || (event.key.toLowerCase() === 'n' && event.ctrlKey)) {
      event.preventDefault();
      this.moveSelection(1, list);
    } else if (event.key === 'ArrowUp' || (event.key.toLowerCase() === 'p' && event.ctrlKey)) {
      event.preventDefault();
      this.moveSelection(-1, list);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const cmd = list.find((c) => c.id === this.selectedId()) ?? list[0];
      if (cmd) this.execute(cmd);
    }
  }

  private moveSelection(delta: number, list: Command[]): void {
    const currentIdx = list.findIndex((c) => c.id === this.selectedId());
    const nextIdx = (currentIdx + delta + list.length) % list.length;
    this.selectedId.set(list[nextIdx].id);
  }
}
