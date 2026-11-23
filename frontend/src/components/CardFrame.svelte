<script lang="ts" module>
  export interface KeyInfo {
    key: string;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey: boolean;
    shiftKey: boolean;
  }
</script>

<script lang="ts">
  import { buildSrcdoc, type FrameOptions } from '../lib/cardFrame';

  interface Props {
    options: FrameOptions;
    focusTyping?: boolean;
    onkey: (key: KeyInfo) => void;
    ontyped: (value: string) => void;
    onsubmit: (value: string) => void;
  }

  let { options, focusTyping = false, onkey, ontyped, onsubmit }: Props = $props();
  let frame: HTMLIFrameElement | undefined = $state();

  const srcdoc = $derived(buildSrcdoc(options));

  function send(type: string): void {
    // The frame has an opaque origin, so '*' is the only target that reaches it.
    frame?.contentWindow?.postMessage({ baw: 1, type }, '*');
  }

  export function replay(): void {
    send('replay');
  }

  $effect(() => {
    function onMessage(event: MessageEvent): void {
      if (!frame || event.source !== frame.contentWindow || !event.data?.baw) return;
      const data = event.data;
      if (data.type === 'key') onkey(data as KeyInfo);
      else if (data.type === 'typed') ontyped(String(data.value ?? ''));
      else if (data.type === 'submit') onsubmit(String(data.value ?? ''));
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  });

  function onload(): void {
    if (focusTyping && frame) {
      // A cross-origin frame may only take focus once its parent hands it over.
      frame.focus();
      send('focus');
    }
  }
</script>

<iframe
  bind:this={frame}
  {srcdoc}
  {onload}
  title="Card"
  sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
  allow="autoplay"
></iframe>

<style>
  iframe {
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
    background: transparent;
  }
</style>
