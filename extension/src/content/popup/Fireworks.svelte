<script lang="ts">
  import { onMount } from 'svelte'

  let { onDone = () => {} } = $props()

  onMount(() => {
    const timer = setTimeout(() => {
      onDone()
    }, 1500)

    return () => clearTimeout(timer)
  })
</script>

<div class="fireworks-overlay">
  <svg class="checkmark" viewBox="0 0 24 24" width="48" height="48">
    <path
      class="check-path"
      d="M 4 12 L 10 18 L 20 6"
      stroke="currentColor"
      stroke-width="2"
      fill="none"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>

  <span class="particle particle-1"></span>
  <span class="particle particle-2"></span>
  <span class="particle particle-3"></span>
  <span class="particle particle-4"></span>
  <span class="particle particle-5"></span>
  <span class="particle particle-6"></span>
  <span class="particle particle-7"></span>
  <span class="particle particle-8"></span>
</div>

<style>
  .fireworks-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    z-index: 9999;
  }

  .checkmark {
    color: #10b981;
    animation: checkDraw 0.4s ease-out forwards;
  }

  .check-path {
    stroke-dasharray: 60;
    stroke-dashoffset: 60;
  }

  @keyframes checkDraw {
    to {
      stroke-dashoffset: 0;
    }
  }

  .particle {
    position: absolute;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    pointer-events: none;
  }

  .particle-1 {
    background: #ef4444;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: 80px;
    --ty: -80px;
  }

  .particle-2 {
    background: #f97316;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: 100px;
    --ty: 0px;
  }

  .particle-3 {
    background: #eab308;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: 80px;
    --ty: 80px;
  }

  .particle-4 {
    background: #22c55e;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: 0px;
    --ty: 100px;
  }

  .particle-5 {
    background: #06b6d4;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: -80px;
    --ty: 80px;
  }

  .particle-6 {
    background: #3b82f6;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: -100px;
    --ty: 0px;
  }

  .particle-7 {
    background: #8b5cf6;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: -80px;
    --ty: -80px;
  }

  .particle-8 {
    background: #ec4899;
    animation: particleBurst 0.8s ease-out forwards;
    --tx: 0px;
    --ty: -100px;
  }

  @keyframes particleBurst {
    0% {
      transform: translate(0, 0) scale(1);
      opacity: 1;
    }
    100% {
      transform: translate(var(--tx), var(--ty)) scale(0);
      opacity: 0;
    }
  }
</style>
