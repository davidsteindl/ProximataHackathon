<script setup>
// CAD-style leader callout: dot on the target, elbow line, mono label. Coordinates in slide px (1280x720).
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
    <circle :cx="at[0]" :cy="at[1]" r="5" :fill="color" />
    <polyline :points="`${at[0]},${at[1]} ${to[0]},${to[1]} ${to[0] + (right ? 16 : -16)},${to[1]}`" :stroke="color" stroke-width="2" fill="none" />
  </svg>
  <div class="leader-label" :style="{ top: `${to[1] - 15}px`, [right ? 'left' : 'right']: `${right ? to[0] + 22 : 1280 - to[0] + 22}px`, borderColor: color }">
    <slot />
  </div>
</template>

<style scoped>
.leader { position: absolute; inset: 0; width: 1280px; height: 720px; pointer-events: none; z-index: 5; }
.leader-label {
  position: absolute; z-index: 6; max-width: 340px; padding: 4px 10px; background: #fff; border: 1.5px solid;
  font: 500 17px/1.3 'JetBrains Mono', monospace; color: #171A1F;
}
</style>
