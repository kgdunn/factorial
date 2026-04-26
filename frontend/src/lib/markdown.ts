import { marked, type TokenizerAndRendererExtension } from 'marked';
import katex from 'katex';
import DOMPurify from 'dompurify';
import 'katex/dist/katex.min.css';

marked.setOptions({ async: false, breaks: true });

interface MathToken {
  text: string;
}

function renderMath(token: unknown, displayMode: boolean): string {
  const { text } = token as MathToken;
  return katex.renderToString(text, {
    displayMode,
    throwOnError: false,
    output: 'html',
  });
}

const inlineMath: TokenizerAndRendererExtension = {
  name: 'inlineMath',
  level: 'inline',
  start(src: string) {
    const idx = src.indexOf('\\(');
    return idx < 0 ? undefined : idx;
  },
  tokenizer(src: string) {
    const match = /^\\\(([\s\S]+?)\\\)/.exec(src);
    if (!match) return undefined;
    return { type: 'inlineMath', raw: match[0], text: match[1] };
  },
  renderer(token) {
    return renderMath(token, false);
  },
};

const blockMath: TokenizerAndRendererExtension = {
  name: 'blockMath',
  level: 'inline',
  start(src: string) {
    const idx = src.indexOf('\\[');
    return idx < 0 ? undefined : idx;
  },
  tokenizer(src: string) {
    const match = /^\\\[([\s\S]+?)\\\]/.exec(src);
    if (!match) return undefined;
    return { type: 'blockMath', raw: match[0], text: match[1] };
  },
  renderer(token) {
    return renderMath(token, true);
  },
};

marked.use({ extensions: [inlineMath, blockMath] });

export function renderMarkdown(text: string): string {
  const raw = marked.parse(text) as string;
  return DOMPurify.sanitize(raw, { ADD_ATTR: ['style'] });
}
