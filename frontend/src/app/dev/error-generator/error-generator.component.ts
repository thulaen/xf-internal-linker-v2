import { CommonModule, DOCUMENT } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-error-generator',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatCardModule, MatIconModule, MatTooltipModule],
  templateUrl: './error-generator.component.html',
  styleUrl: './error-generator.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ErrorGeneratorComponent {
  private readonly http = inject(HttpClient);
  private readonly document = inject(DOCUMENT);

  triggerUncaught(): void {
    throw new Error('Slice 3 uncaught smoke');
  }

  triggerRejection(): Promise<never> {
    return Promise.reject(new Error('Slice 3 rejection smoke'));
  }

  triggerNetwork(): void {
    this.http.get('/api/__nonexistent_' + crypto.randomUUID()).subscribe();
  }

  triggerConsole(): void {
    console.error('Slice 3 console smoke');
  }

  triggerCls(): void {
    const bodyStyle = this.document.body.style;
    const previousMarginTop = bodyStyle.marginTop;

    window.setTimeout(() => {
      bodyStyle.marginTop = '200px';

      window.setTimeout(() => {
        bodyStyle.marginTop = previousMarginTop;
      }, 100);
    }, 600);
  }
}
