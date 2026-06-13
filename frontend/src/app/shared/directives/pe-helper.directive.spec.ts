import { Component, ChangeDetectionStrategy } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { MatTooltip, MatTooltipModule } from '@angular/material/tooltip';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { PeHelperDirective, resolveGlossaryDefinition } from './pe-helper.directive';

@Component({
  standalone: true,
  imports: [PeHelperDirective, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `<span [peHelper]="term">Target</span>`,
})
class HostComponent {
  term = 'Embedding';
}

describe('PeHelperDirective', () => {
  let fixture: ComponentFixture<HostComponent>;
  let spanEl: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HostComponent, NoopAnimationsModule],
    }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    spanEl = fixture.debugElement.query(By.css('span')).nativeElement;
    fixture.detectChanges();
  });

  it('Given a glossary term, When the directive initializes, Then it sets the data-pe-helper attribute', () => {
    expect(spanEl.hasAttribute('data-pe-helper')).toBe(true);
  });

  it('Given a known glossary term, When the directive binds to the element, Then it attaches the matTooltip behavior with the resolved definition', () => {
    const tooltip = fixture.debugElement.query(By.css('span')).injector.get(MatTooltip);
    expect(tooltip.message.toLowerCase()).toContain('meaning');
  });
});

describe('resolveGlossaryDefinition (peHelper)', () => {
  it('Given a known term, When resolveGlossaryDefinition is called, Then it returns the glossary definition', () => {
    const got = resolveGlossaryDefinition('Embedding');
    expect(got.toLowerCase()).toContain('meaning');
  });

  it('Given a lowercase term, When resolveGlossaryDefinition is called, Then it normalises case and returns the matching definition', () => {
    // 'embedding' (lowercase) must still resolve to the 'Embedding' glossary
    // entry, proving the lookup normalises case before matching.
    const got = resolveGlossaryDefinition('embedding');
    expect(got.toLowerCase()).toContain('meaning');
  });

  it('Given a multi-word sentence, When resolveGlossaryDefinition is called, Then it returns the input verbatim', () => {
    const input = 'click here to refresh the table';
    expect(resolveGlossaryDefinition(input)).toBe(input);
  });

  it('Given an unknown single-word term, When resolveGlossaryDefinition is called, Then it returns a flagged string stating no entry exists', () => {
    const got = resolveGlossaryDefinition('xyzabc');
    expect(got).toContain('xyzabc');
    expect(got).toContain('no glossary entry');
  });

  it('Given an empty string, When resolveGlossaryDefinition is called, Then it returns an empty string', () => {
    expect(resolveGlossaryDefinition('')).toBe('');
  });
});
