import { describe, expect, it } from 'vitest';
import { firstName, initials } from './format';

describe('firstName', () => {
  it('returns the first word of a display name', () => {
    expect(firstName('Pat Example')).toBe('Pat');
    expect(firstName('Dr. Rivera')).toBe('Dr.');
  });

  it('handles a single name', () => {
    expect(firstName('Pat')).toBe('Pat');
  });

  it('is empty and never throws when there is no name', () => {
    expect(firstName('')).toBe('');
    expect(firstName('   ')).toBe('');
  });

  it('ignores leading/collapsing whitespace', () => {
    expect(firstName('  Pat   Example ')).toBe('Pat');
  });
});

describe('initials', () => {
  it('returns up to two uppercase initials', () => {
    expect(initials('Pat Example')).toBe('PE');
    expect(initials('Pat')).toBe('P');
  });

  it('falls back to ? when there is no name', () => {
    expect(initials('')).toBe('?');
    expect(initials('   ')).toBe('?');
  });
});
