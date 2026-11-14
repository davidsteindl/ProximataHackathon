<script setup>
// Drawing-sheet frame on every slide: border, title block, optional structural grid axes.
import { computed } from 'vue'
import { useSlideContext } from '@slidev/client'

const { $frontmatter, $page, $nav } = useSlideContext()
const dark = computed(() => $frontmatter.class === 'sheet-dark')
const sheet = computed(() => `P-${String($page.value).padStart(2, '0')}`)
const total = computed(() => `P-${String($nav.value.total).padStart(2, '0')}`)
</script>

<template>
  <div class="sheet" :class="{ dark }">
    <div class="frame" />
    <template v-if="$frontmatter.axes">
      <span v-for="(a, i) in ['A', 'B', 'C', 'D']" :key="a" class="axis" :style="{ left: `${170 + i * 300}px`, top: '2px' }">{{ a }}</span>
      <span v-for="(a, i) in ['1', '2', '3']" :key="a" class="axis" :style="{ left: '2px', top: `${150 + i * 200}px` }">{{ a }}</span>
    </template>
    <div class="titleblock">
      <div class="cell wide"><b>GroundIQ · Pitch</b><span>{{ $frontmatter.sheet }}</span></div>
      <div class="cell"><small>Sheet</small><b>{{ sheet }}</b><span>of {{ total }}</span></div>
      <div class="cell"><small>Rev</small><b>D</b></div>
      <div class="cell"><small>Date</small><b>2026-11-14</b></div>
    </div>
  </div>
</template>

<style scoped>
.sheet { position: absolute; inset: 0; pointer-events: none; z-index: 10; --ink: #171A1F; --line: rgba(23, 26, 31, .55); --paper: #EDF1F5; }
.sheet.dark { --ink: #EDF1F5; --line: rgba(237, 241, 245, .4); --paper: #0E1116; }
.frame { position: absolute; inset: 14px; border: 1.5px solid var(--line); }
.axis {
  position: absolute; width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid var(--line);
  background: var(--paper); color: var(--ink); font: 600 12px/21px 'JetBrains Mono', monospace; text-align: center;
}
.titleblock {
  position: absolute; right: 14px; bottom: 14px; display: flex; background: var(--paper);
  border-top: 1.5px solid var(--line); border-left: 1.5px solid var(--line);
  font-family: 'JetBrains Mono', monospace; color: var(--ink);
}
.cell { display: flex; flex-direction: column; justify-content: center; padding: 5px 12px; border-left: 1px solid var(--line); min-width: 56px; }
.cell:first-child { border-left: 0; }
.cell.wide { min-width: 210px; }
.cell small { font-size: 9px; text-transform: uppercase; opacity: .6; letter-spacing: .06em; }
.cell b { font-size: 13px; font-weight: 600; }
.cell span { font-size: 10px; opacity: .7; }
</style>
