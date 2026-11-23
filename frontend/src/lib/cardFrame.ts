import type { AvTag } from './types';

/**
 * Cards render inside a sandboxed iframe (scripts allowed, but no access to this app's
 * origin, cookies or API). It is close to how desktop Anki shows cards: the note type's
 * CSS and scripts apply, and `.card` is on <body>. A small bridge script plays audio and
 * forwards key presses and the typed answer to the app via postMessage.
 */

export interface FrameOptions {
  html: string;
  css: string;
  ord: number;
  mediaBase: string; // absolute URL ending in '/'
  av: { q: AvTag[]; a: AvTag[] };
  side: 'q' | 'a';
  autoplay: boolean;
  replayQuestion: boolean;
  night: boolean;
}

const MATHJAX_URL = 'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml-full.js';

// Defaults close to desktop's reviewer stylesheet; the note type's CSS comes after
// and can override all of it.
const BASE_CSS = `
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; padding: 20px 16px 40px; min-height: 100vh; box-sizing: border-box; overflow-wrap: break-word; }
body.nightMode.card { color: #e9ecef; background-color: #1f2329; }
img { max-width: 100%; max-height: 95vh; height: auto; }
.nightMode img.latex { filter: invert(100%); }
hr#answer { border: none; border-top: 1px solid #c8ccd2; margin: 1em 0; }
.nightMode hr#answer { border-top-color: #4a515b; }
#typeans { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid #b6bcc5; border-radius: 6px; }
.nightMode #typeans { background: #2a2f37; color: #e9ecef; border-color: #4a515b; }
code#typeans { display: block; font-family: ui-monospace, Menlo, Consolas, monospace; white-space: pre-wrap; }
.typeGood { background-color: #afa; color: black; }
.typeBad { background-color: #faa; color: black; }
.typeMissed { background-color: #ccc; color: black; }
.replay-button { display: inline-block; vertical-align: middle; margin: 4px; text-decoration: none; }
.replay-button svg { width: 40px; height: 40px; }
.replay-button svg circle { fill: #fff; stroke: #414141; stroke-width: 2px; }
.replay-button svg path { fill: #414141; }
.nightMode .replay-button svg circle { fill: #3a3f47; stroke: #e9ecef; }
.nightMode .replay-button svg path { fill: #e9ecef; }
.baw-video { max-width: 100%; display: block; margin: 8px auto; }
`;

// Plain ES5 so it runs before (and independently of) whatever the card's own JS does.
const BRIDGE_JS = `(function () {
  var cfg = window.__baw;
  function post(message) { message.baw = 1; parent.postMessage(message, '*'); }
  var current = null, queue = [];
  function stop() {
    queue = [];
    if (current) { try { current.pause(); } catch (e) {} current = null; }
    if (window.speechSynthesis) speechSynthesis.cancel();
  }
  function playNext() {
    var tag = queue.shift();
    current = null;
    if (!tag) return;
    if (tag.kind === 'audio') {
      var audio = new Audio(cfg.base + encodeURIComponent(tag.file));
      current = audio;
      audio.onended = playNext;
      audio.onerror = playNext;
      var p = audio.play();
      if (p && p.catch) p.catch(function () { queue = []; current = null; });
    } else if (tag.kind === 'video') {
      var video = document.querySelector('video[data-av="' + tag.ref + '"]');
      if (!video) return playNext();
      current = video;
      video.onended = playNext;
      var vp = video.play();
      if (vp && vp.catch) vp.catch(function () {});
    } else if (tag.kind === 'tts' && window.speechSynthesis) {
      var text = String(tag.text || '').replace(/<[^>]*>/g, ' ');
      var u = new SpeechSynthesisUtterance(text);
      if (tag.lang) u.lang = String(tag.lang).replace('_', '-');
      if (tag.speed) u.rate = tag.speed;
      u.onend = playNext;
      speechSynthesis.speak(u);
    } else {
      playNext();
    }
  }
  function tagsFor(side) {
    return (cfg.av[side] || []).map(function (t, i) {
      var copy = {}; for (var k in t) copy[k] = t[k];
      copy.ref = side + ':' + i;
      return copy;
    });
  }
  function play(list) { stop(); queue = list; playNext(); }
  function replay() {
    if (cfg.side === 'q') play(tagsFor('q'));
    else play((cfg.replayQuestion ? tagsFor('q') : []).concat(tagsFor('a')));
  }
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest ? e.target.closest('a[data-av]') : null;
    if (!el) return;
    e.preventDefault();
    var parts = el.getAttribute('data-av').split(':');
    var tag = tagsFor(parts[0])[Number(parts[1])];
    if (tag) play([tag]);
  });
  document.addEventListener('keydown', function (e) {
    var t = e.target || {};
    if (t.id === 'typeans') {
      if (e.key === 'Enter') { e.preventDefault(); post({ type: 'submit', value: t.value }); }
      return;
    }
    if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || '')) return;
    if (e.key === ' ' || e.key === 'Enter') e.preventDefault();
    post({ type: 'key', key: e.key, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, shiftKey: e.shiftKey });
  });
  document.addEventListener('input', function (e) {
    if (e.target && e.target.id === 'typeans') post({ type: 'typed', value: e.target.value });
  });
  window.addEventListener('message', function (e) {
    if (e.source !== parent || !e.data || !e.data.baw) return;
    if (e.data.type === 'replay') replay();
    else if (e.data.type === 'stop') stop();
    else if (e.data.type === 'focus') {
      var input = document.getElementById('typeans');
      if (input) input.focus();
    }
  });
  window.addEventListener('pagehide', stop);
  window.addEventListener('load', function () {
    if (cfg.autoplay) play(tagsFor(cfg.side));
  });
})();`;

function escapeAttr(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

export function buildSrcdoc(o: FrameOptions): string {
  const needsMath = /\\\(|\\\[/.test(o.html);
  const mobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  const classes = ['card', `card${o.ord + 1}`, 'isWeb'];
  if (o.night) classes.push('nightMode', 'night_mode');
  if (mobile) classes.push('mobile', 'isMobile');

  const config = JSON.stringify({
    av: o.av,
    side: o.side,
    autoplay: o.autoplay,
    replayQuestion: o.replayQuestion,
    base: o.mediaBase,
  }).replace(/</g, '\\u003c');

  const mathjax = needsMath
    ? `<script>window.MathJax = { tex: { inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']], processEscapes: false }, options: { ignoreHtmlClass: 'tex2jax_ignore' }, startup: { typeset: true } };</script>` +
      `<script async src="${MATHJAX_URL}"></script>`
    : '';

  // A stray "</style>" in user CSS would otherwise end the style block early.
  const css = o.css.replace(/<\/style/gi, '<\\/style');

  return (
    '<!doctype html><html><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    `<meta name="color-scheme" content="${o.night ? 'dark' : 'light'}">` +
    `<base href="${escapeAttr(o.mediaBase)}" target="_blank">` +
    `<style>${BASE_CSS}</style><style>${css}</style>${mathjax}</head>` +
    `<body class="${classes.join(' ')}"><div id="qa">${o.html}</div>` +
    `<script>window.__baw = ${config};</script><script>${BRIDGE_JS}</script>` +
    '</body></html>'
  );
}
