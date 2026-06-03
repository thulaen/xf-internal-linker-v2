import { resolveGlossaryDefinition } from './pe-helper.directive';

describe('resolveGlossaryDefinition (peHelper)', () => {
  it('returns a glossary definition for a known term', () => {
    const got = resolveGlossaryDefinition('Embedding');
    expect(got.toLowerCase()).toContain('meaning');
  });

  it('is case-insensitive', () => {
    // 'embedding' (lowercase) must still resolve to the 'Embedding' glossary
    // entry, proving the lookup normalises case before matching.
    const got = resolveGlossaryDefinition('embedding');
    expect(got.toLowerCase()).toContain('meaning');
  });

  it('returns the input verbatim when it is a sentence (multi-word, unknown)', () => {
    const input = 'click here to refresh the table';
    expect(resolveGlossaryDefinition(input)).toBe(input);
  });

  it('flags unknown single-word terms so authors can spot the gap', () => {
    const got = resolveGlossaryDefinition('xyzabc');
    expect(got).toContain('xyzabc');
    expect(got).toContain('no glossary entry');
  });

  it('returns an empty string when term is empty', () => {
    expect(resolveGlossaryDefinition('')).toBe('');
  });
});
