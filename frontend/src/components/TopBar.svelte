<script lang="ts">
  import Icon from './Icon.svelte';
  import SyncBadge from './SyncBadge.svelte';
  import { router } from '../lib/router.svelte';
</script>

<header class="topbar">
  <div class="inner">
    <a class="brand" href="#/">
      <img src="/favicon.svg" alt="" width="24" height="24" />
      <span>Better Anki</span>
    </a>
    <nav>
      <a class="nav-link decks-link" class:active={router.route.name === 'decks'} href="#/">Decks</a>
      <a
        class="nav-link search-link"
        class:active={router.route.name === 'search'}
        href="#/search"
        aria-label="Search"
        title="Search cards"
      >
        <Icon name="search" size={17} />
        <span>Search</span>
      </a>
      <a class="btn primary small" class:active={router.route.name === 'add'} href="#/add">
        <Icon name="plus" size={16} />
        <span>Add</span>
      </a>
      <SyncBadge />
      <a
        class="icon-btn"
        class:active={router.route.name === 'settings'}
        href="#/settings"
        aria-label="Settings"
        title="Settings"
      >
        <Icon name="settings" />
      </a>
    </nav>
  </div>
</header>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 10;
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--surface) 92%, transparent);
    backdrop-filter: blur(8px);
    padding-top: env(safe-area-inset-top);
  }
  .inner {
    display: flex;
    align-items: center;
    gap: 12px;
    max-width: 960px;
    height: 56px;
    margin: 0 auto;
    padding: 0 16px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-right: auto;
    color: var(--text);
    font-weight: 700;
    text-decoration: none;
  }
  nav {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .nav-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 8px;
    color: var(--muted);
    text-decoration: none;
    font-weight: 500;
  }
  .nav-link:hover,
  .nav-link.active {
    color: var(--text);
    background: var(--surface-2);
  }
  .icon-btn.active {
    color: var(--text);
    background: var(--surface-2);
  }
  @media (max-width: 520px) {
    .brand span,
    .decks-link,
    .search-link span {
      display: none;
    }
    nav {
      gap: 6px;
    }
  }
</style>
