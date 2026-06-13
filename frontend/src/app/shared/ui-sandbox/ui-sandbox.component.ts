import { ChangeDetectionStrategy, Component } from '@angular/core';

import { CardDirective } from '../ui/card/card.directive';
import { ButtonDirective } from '../ui/button/button.directive';
import { SpinnerComponent } from '../ui/spinner/spinner.component';
import { DividerDirective } from '../ui/divider/divider.directive';
import { ChipComponent } from '../ui/chip/chip.component';

/**
 * Public component gallery for the owned shadcn-style primitives (CDK +
 * Tailwind, Material-free). Served at the unguarded route `/ui-sandbox` so each
 * primitive can be verified in isolation (computed CSS via the live preview)
 * without the app shell's auth redirect or its always-on polling. This is the
 * Phase B verification surface — every new primitive gets a row here before it
 * is rolled out across the app. See GSC-DESIGN-SYSTEM.md.
 */
@Component({
  selector: 'app-ui-sandbox',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
  imports: [CardDirective, ButtonDirective, SpinnerComponent, DividerDirective, ChipComponent],
  template: `
    <div class="flex max-w-xl flex-col gap-6 p-8">
      <h1 class="text-xl font-normal">UI primitive sandbox</h1>

      <div appCard id="card-default">
        <h2 class="mb-2 text-base font-medium">Card — default padding (24px)</h2>
        <p class="m-0">
          Flat white GSC surface: 0.8px hairline border, 12px radius, white
          fill, no resting shadow.
        </p>
      </div>

      <section appCard padding="dense" id="card-dense">
        <p class="m-0">Card — dense padding (16px).</p>
      </section>

      <div class="flex gap-3" id="btn-row">
        <button appBtn>Primary</button>
        <button appBtn variant="outline">Outline</button>
        <button appBtn variant="ghost">Ghost</button>
      </div>

      <div class="flex items-center gap-6" id="spinner-row">
        <app-spinner size="sm"></app-spinner>
        <app-spinner size="md"></app-spinner>
        <app-spinner size="lg"></app-spinner>
      </div>

      <hr appDivider id="divider-h" />

      <div class="flex gap-2" id="chip-row">
        <app-chip>Draft</app-chip>
        <app-chip tone="primary">Active</app-chip>
        <app-chip tone="primary" [removable]="true">Filter</app-chip>
      </div>
    </div>
  `,
})
export class UiSandboxComponent {}
