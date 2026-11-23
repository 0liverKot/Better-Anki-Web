/**
 * MathJax for the editor's live preview (cards in review load their own copy inside the
 * sandboxed card frame). Loaded on first use.
 *
 * Formulas are rendered to SVG and shown as <img> data URLs, as Anki's editor does: an
 * image can't run scripts or hold clickable links, so TeX from a shared deck can't do
 * anything in this page. MathJax's "safe" extension is enabled as well.
 */

const MATHJAX_URL = 'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js';

export interface RenderedMath {
  src: string;
  width: string;
  height: string;
  verticalAlign: string;
}

let loading: Promise<any> | null = null;
let queue: Promise<unknown> = Promise.resolve();

function loadMathJax(): Promise<any> {
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      (window as any).MathJax = {
        loader: { load: ['ui/safe'] },
        tex: { inlineMath: [], displayMath: [] }, // we render explicitly, never scan the page
        svg: { fontCache: 'local' }, // each SVG carries its own glyphs, so it works as an image
        options: { enableMenu: false },
        startup: { typeset: false },
      };
      const script = document.createElement('script');
      script.src = MATHJAX_URL;
      script.async = true;
      script.onload = () => (window as any).MathJax.startup.promise.then(() => resolve((window as any).MathJax));
      script.onerror = () => {
        loading = null;
        script.remove();
        reject(new Error("Couldn't load MathJax."));
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

/** Render TeX to an SVG image. `color` replaces MathJax's currentColor, which an <img> can't inherit. */
export function renderTex(tex: string, block: boolean, color: string): Promise<RenderedMath | null> {
  // MathJax isn't re-entrant; run renders one at a time.
  const job = queue.then(async () => {
    const mathjax = await loadMathJax();
    mathjax.texReset();
    const node: HTMLElement = await mathjax.tex2svgPromise(tex, { display: block });
    const svg = node.querySelector('svg');
    if (!svg) return null;
    const markup = svg.outerHTML.replace(/currentColor/g, color);
    return {
      src: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`,
      width: svg.getAttribute('width') ?? '',
      height: svg.getAttribute('height') ?? '',
      verticalAlign: svg.style.verticalAlign,
    };
  });
  queue = job.catch(() => {});
  return job;
}
