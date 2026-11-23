<script lang="ts">
  import { onMount } from 'svelte';
  import Toasts from './components/Toasts.svelte';
  import TopBar from './components/TopBar.svelte';
  import { api } from './lib/api';
  import { router } from './lib/router.svelte';
  import { session } from './lib/session.svelte';
  import { startSync } from './lib/sync.svelte';
  import Add from './routes/Add.svelte';
  import Decks from './routes/Decks.svelte';
  import Login from './routes/Login.svelte';
  import Review from './routes/Review.svelte';
  import Search from './routes/Search.svelte';
  import Settings from './routes/Settings.svelte';

  let unreachable = $state(false);

  async function checkSession(): Promise<void> {
    try {
      const me = await api<{ authenticated: boolean }>('/api/auth/me');
      session.authenticated = me.authenticated;
      unreachable = false;
    } catch {
      unreachable = true;
      setTimeout(checkSession, 3000);
    }
  }

  onMount(checkSession);

  $effect(() => {
    if (session.authenticated) startSync();
  });
</script>

{#if session.authenticated === null}
  <div class="splash muted">{unreachable ? "Can't reach the server. Retrying…" : 'Loading…'}</div>
{:else if !session.authenticated}
  <Login />
{:else}
  {#if router.route.name === 'review'}
    {#key router.route.deckId}
      <Review deckId={router.route.deckId} />
    {/key}
  {:else}
    <TopBar />
    {#if router.route.name === 'add'}
      <Add />
    {:else if router.route.name === 'search'}
      <Search />
    {:else if router.route.name === 'settings'}
      <Settings />
    {:else}
      <Decks />
    {/if}
  {/if}
{/if}

<Toasts />

<style>
  .splash {
    display: grid;
    place-items: center;
    min-height: 100vh;
  }
</style>
