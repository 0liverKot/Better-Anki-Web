import type { DeckNode } from './types';

/** A deck id to drop into, 'root' to make it a top-level deck, or null for nowhere. */
export type DropTarget = number | 'root' | null;

interface Options {
  find: (id: number) => DeckNode | null;
  canDrop: (source: DeckNode, target: number | 'root') => boolean;
  ondrop: (source: DeckNode, target: number | 'root') => void;
}

interface Gesture {
  deck: DeckNode;
  pointerId: number;
  touch: boolean;
  startX: number;
  startY: number;
  x: number;
  y: number;
  timer?: ReturnType<typeof setTimeout>;
  /** Esc was pressed: ignore the rest of this press. */
  cancelled?: boolean;
}

const LONG_PRESS_MS = 400; // touch: hold this long to pick a deck up (shorter moves scroll)
const MOUSE_SLOP = 6; // mouse: move this far to start dragging (less is a click)
const TOUCH_SLOP = 10;
const EDGE = 64; // dragging this close to the top/bottom of the screen scrolls the page

/**
 * Dragging decks onto other decks, with pointer events so it works with a mouse
 * (press and move) and on touch screens (press and hold, then move), where the
 * HTML drag-and-drop API isn't available. Rows are found by `data-deck-id`, and
 * the element that makes a deck top-level by `data-drop-root`.
 */
export class DeckDrag {
  source = $state<DeckNode | null>(null);
  target = $state<DropTarget>(null);
  x = $state(0);
  y = $state(0);
  touch = $state(false);

  #gesture: Gesture | null = null;
  #frame = 0;
  #opts: Options;

  constructor(opts: Options) {
    this.#opts = opts;
  }

  /** Attach to `pointerdown` on the element containing the deck rows. */
  pointerdown = (event: PointerEvent): void => {
    if (this.#gesture || !event.isPrimary || event.button !== 0) return;
    const el = event.target as Element;
    if (el.closest('button, input, select, textarea, form')) return;
    const row = el.closest<HTMLElement>('[data-deck-id]');
    const deck = row && this.#opts.find(Number(row.dataset.deckId));
    if (!deck) return;
    const { clientX: x, clientY: y } = event;
    const touch = event.pointerType === 'touch';
    this.#gesture = { deck, pointerId: event.pointerId, touch, startX: x, startY: y, x, y };
    if (touch) this.#gesture.timer = setTimeout(() => this.#start(), LONG_PRESS_MS);
    this.#listen(true);
  };

  destroy(): void {
    this.#end();
  }

  #start(): void {
    const g = this.#gesture;
    if (!g) return;
    clearTimeout(g.timer);
    this.source = g.deck;
    this.touch = g.touch;
    document.body.classList.add('deck-dragging');
    getSelection()?.removeAllRanges();
    if (g.touch) navigator.vibrate?.(15);
    this.#update(g.x, g.y);
    this.#frame = requestAnimationFrame(this.#autoscroll);
  }

  #update(x: number, y: number): void {
    const source = this.source;
    if (!source) return;
    this.x = x;
    this.y = y;
    const el = document.elementFromPoint(x, y);
    let target: DropTarget = null;
    if (el?.closest('[data-drop-root]')) {
      target = 'root';
    } else {
      const row = el?.closest<HTMLElement>('[data-deck-id]');
      if (row) target = Number(row.dataset.deckId);
    }
    this.target = target !== null && this.#opts.canDrop(source, target) ? target : null;
  }

  #autoscroll = (): void => {
    if (!this.source) return;
    const top = document.querySelector('.topbar')?.getBoundingClientRect().bottom ?? 0;
    let dy = 0;
    if (this.y < top + EDGE) dy = -(top + EDGE - this.y);
    else if (this.y > innerHeight - EDGE) dy = this.y - (innerHeight - EDGE);
    if (dy) {
      const before = scrollY;
      scrollBy(0, Math.max(-18, Math.min(18, Math.round(dy / 3))));
      // The rows moved under the pointer.
      if (scrollY !== before) this.#update(this.x, this.y);
    }
    this.#frame = requestAnimationFrame(this.#autoscroll);
  };

  #move = (event: PointerEvent): void => {
    const g = this.#gesture;
    if (!g || event.pointerId !== g.pointerId || g.cancelled) return;
    if (this.source) {
      this.#update(event.clientX, event.clientY);
      return;
    }
    g.x = event.clientX;
    g.y = event.clientY;
    const moved = Math.hypot(g.x - g.startX, g.y - g.startY);
    if (g.touch) {
      if (moved > TOUCH_SLOP) this.#end(); // it's a scroll, not a long press
    } else if (moved > MOUSE_SLOP) {
      this.#start();
    }
  };

  #up = (event: PointerEvent): void => {
    const g = this.#gesture;
    if (!g || event.pointerId !== g.pointerId) return;
    const { source, target } = this;
    if (source || g.cancelled) this.#swallowClick();
    this.#end();
    if (source && target !== null) this.#opts.ondrop(source, target);
  };

  #cancel = (event: PointerEvent): void => {
    if (event.pointerId === this.#gesture?.pointerId) this.#end();
  };

  #keydown = (event: KeyboardEvent): void => {
    if (event.key !== 'Escape' || !this.source || !this.#gesture) return;
    event.preventDefault();
    this.#gesture.cancelled = true;
    this.source = null;
    this.target = null;
    document.body.classList.remove('deck-dragging');
  };

  // Touch: no context menu on a long press, and no scrolling while dragging
  // (auto-scroll at the screen edges takes over).
  #contextmenu = (event: Event): void => {
    if (this.#gesture?.touch) event.preventDefault();
  };
  #touchmove = (event: TouchEvent): void => {
    if (this.source && event.cancelable) event.preventDefault();
  };

  /** The press that ended a drag mustn't also click the deck link (opening it). */
  #swallowClick(): void {
    const swallow = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener('click', swallow, { capture: true, once: true });
    setTimeout(() => window.removeEventListener('click', swallow, { capture: true }), 400);
  }

  #listen(on: boolean): void {
    const method = on ? 'addEventListener' : 'removeEventListener';
    window[method]('pointermove', this.#move as EventListener);
    window[method]('pointerup', this.#up as EventListener);
    window[method]('pointercancel', this.#cancel as EventListener);
    window[method]('keydown', this.#keydown as EventListener);
    window[method]('contextmenu', this.#contextmenu);
    window[method]('touchmove', this.#touchmove as EventListener, { passive: false });
  }

  #end(): void {
    if (this.#gesture) {
      clearTimeout(this.#gesture.timer);
      this.#listen(false);
    }
    this.#gesture = null;
    this.source = null;
    this.target = null;
    cancelAnimationFrame(this.#frame);
    document.body.classList.remove('deck-dragging');
  }
}
