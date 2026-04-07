import { Pipe, PipeTransform } from '@angular/core';
import { SecurityContext } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { highlightText } from '../utils/highlight.utils';

@Pipe({
  name: 'highlight',
  standalone: true,
  pure: true
})
export class HighlightPipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {}

  transform(text: string | null | undefined, phrase: string | null | undefined): SafeHtml {
    if (!text) return '';
    if (!phrase) return text;

    const highlighted = highlightText(text, phrase);
    // sanitize() runs Angular's full HTML sanitizer on the already-escaped
    // string, so any regression in highlightText() cannot produce XSS.
    // bypassSecurityTrustHtml() is intentionally avoided here.
    const sanitized = this.sanitizer.sanitize(SecurityContext.HTML, highlighted) ?? '';
    return this.sanitizer.bypassSecurityTrustHtml(sanitized);
  }
}
