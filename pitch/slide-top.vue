<script setup>
// Slim footer on every slide: project and sheet name on the left, sheet number, revision and date on the right.
import { computed } from 'vue'
import { useSlideContext } from '@slidev/client'

const { $frontmatter, $page, $nav } = useSlideContext()
const dark = computed(() => $frontmatter.class === 'sheet-dark')
const sheet = computed(() => `P-${String($page.value).padStart(2, '0')}`)
const total = computed(() => `P-${String($nav.value.total).padStart(2, '0')}`)
</script>

<template>
  <div class="sheet" :class="{ dark }">
    <div class="foot left"><b>GroundIQ · Pitch</b><span class="dot" />{{ $frontmatter.sheet }}</div>
    <div class="foot right">
      <span>Sheet <b>{{ sheet }}</b> of {{ total }}</span>
      <span>Rev <b>D</b></span>
      <span>Date <b>2026-11-14</b></span>
    </div>
  </div>
</template>

<style scoped>
.sheet { position: absolute; inset: 0; pointer-events: none; z-index: 10; --fg: #7A8699; --strong: #171A1F; --accent: #176AC6; }
.sheet.dark { --fg: #8DC0F5; --strong: #FFFFFF; --accent: #5AA2EE; }
.foot { position: absolute; bottom: 24px; display: flex; align-items: center; gap: 10px; font: 400 13px/1 'IBM Plex Mono', monospace; color: var(--fg); }
.foot b { font-weight: 600; color: var(--strong); }
.left { left: 64px; }
.right { right: 64px; gap: 22px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
</style>
