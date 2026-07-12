<script lang="ts">
  import Header from './lib/Header.svelte';
  import TrackList from './lib/TrackList.svelte';
  import TrackGrid from './lib/TrackGrid.svelte';
  import Mixer from './lib/Mixer.svelte';
  import ApiGenerator from './lib/ApiGenerator.svelte';
  import StyleTransfer from './lib/StyleTransfer.svelte';
  import KeyboardSynth from './lib/KeyboardSynth.svelte';
  import './lib/audioEngine'; // Initialize the audio engine
</script>

<main>
  <Header />
  
  <div class="top-panels">
    <ApiGenerator />
    <StyleTransfer />
  </div>

  <div class="workspace">
    <div class="timeline-container">
      <TrackList />
      <TrackGrid />
    </div>
  </div>

  <div class="bottom-panels">
    <Mixer />
    <KeyboardSynth />
  </div>
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100vw;
  }

  .top-panels {
    display: flex;
    background: var(--card-bg);
  }

  .bottom-panels {
    display: flex;
    border-top: 1px solid var(--border);
  }
  
  .bottom-panels > :global(.mixer) {
    flex: 1;
    border-top: none;
    border-right: 1px solid var(--border);
  }

  .workspace {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .timeline-container {
    flex: 1;
    display: flex;
    overflow: hidden;
  }
</style>
