/**
 * Tests for ``renderMarkdown`` — the marked + KaTeX + DOMPurify pipeline
 * used by the chat agent message bubbles.
 *
 * The two math cases are the canary for the backslash-escape gotcha:
 * marked's default tokeniser eats ``\(`` as an escape for ``(``. Our
 * custom inline / block extensions must take priority via their start()
 * functions; if they don't, these tests fail with no ``katex`` class in
 * the output.
 */
import { describe, expect, it } from 'vitest';

import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
  it('typesets inline math wrapped in \\( ... \\)', () => {
    const html = renderMarkdown('Use a \\(2^{5-1}_{V}\\) design.');
    expect(html).toContain('class="katex"');
    // KaTeX renders the literal text into <span class="mord">...; the raw
    // LaTeX source must NOT remain in the output.
    expect(html).not.toContain('\\(');
    expect(html).not.toContain('2^{5-1}');
  });

  it('typesets display math wrapped in \\[ ... \\] with displayMode', () => {
    const html = renderMarkdown('Confounding: \\[E = ABCD\\]');
    expect(html).toContain('class="katex"');
    // displayMode: true wraps the result in katex-display.
    expect(html).toContain('katex-display');
    expect(html).not.toContain('\\[');
  });

  it('passes through plain prose unchanged (no math, no KaTeX)', () => {
    const html = renderMarkdown('Just a normal sentence.');
    expect(html).toContain('Just a normal sentence.');
    expect(html).not.toContain('katex');
  });

  it('does not treat literal dollar amounts as math', () => {
    const html = renderMarkdown('The kit costs $200 and ships next week.');
    expect(html).toContain('$200');
    expect(html).not.toContain('katex');
  });

  it('still renders standard markdown (bold, code, lists)', () => {
    const html = renderMarkdown('**bold** and `code`');
    expect(html).toContain('<strong>bold</strong>');
    expect(html).toContain('<code>code</code>');
  });
});
