import { Pipe, PipeTransform } from '@angular/core';
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
    return this.sanitizer.bypassSecurityTrustHtml(highlighted);
  }
}
