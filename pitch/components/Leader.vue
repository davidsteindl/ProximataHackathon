<script setup>
// Leader callout: dot on the target, elbow line, label pill. Coordinates in slide px (1280x720).
const props = defineProps({
  at: { type: Array, required: true },   // [x, y] point on the drawing / screenshot
  to: { type: Array, required: true },   // [x, y] where the label starts
  tone: { type: String, default: 'blue' }, // blue | red | ink
})
const color = { blue: '#176AC6', red: '#E2492F', ink: '#171A1F' }[props.tone]
const right = props.to[0] >= props.at[0]
</script>

<template>
  <svg class="leader" viewBox="0 0 1280 720">
    <circle :cx="at[0]" :cy="at[1]" r="9" :fill="color" fill-opacity=".18" />
    <circle :cx="at[0]" :cy="at[1]" r="4.5" :fill="color" />
    <polyline :points="`${at[0]},${at[1]} ${to[0]},${to[1]} ${to[0] + (right ? 16 : -16)},${to[1]}`" :stroke="color" stroke-width="1.75" fill="none" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
  <div class="leader-label" :style="{ top: `${to[1] - 17}px`, [right ? 'left' : 'right']: `${right ? to[0] + 22 : 1280 - to[0] + 22}px`, '--c': color }">
    <slot />
  </div>
</template>

<style scoped>
.leader { position: absolute; inset: 0; width: 1280px; height: 720px; pointer-events: none; z-index: 5; }
.leader-label {
  position: absolute; z-index: 6; max-width: 340px; padding: 7px 14px; background: #fff; border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--c) 35%, transparent);
  box-shadow: 0 8px 20px rgba(15, 76, 147, .12);
  font: 500 15px/1.3 'IBM Plex Mono', monospace; color: #171A1F;
}
</style>
