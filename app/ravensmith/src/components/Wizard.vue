<script setup lang="ts">
import { ref, computed } from "vue";

interface WizardStep {
  /** Short title rendered in the step indicator (e.g. "Choose hero"). */
  title: string;
}

const props = defineProps<{
  steps: WizardStep[];
}>();

const currentIndex = ref(0);

const isFirst = computed(() => currentIndex.value === 0);
const isLast = computed(() => currentIndex.value === props.steps.length - 1);

function back() {
  if (!isFirst.value) currentIndex.value -= 1;
}

function next() {
  if (!isLast.value) currentIndex.value += 1;
}

defineExpose({ currentIndex, back, next });
</script>

<template>
  <div class="flex flex-col gap-4">
    <ol class="flex gap-2 text-sm">
      <li
        v-for="(step, idx) in steps"
        :key="idx"
        class="px-3 py-1 rounded border"
        :class="
          idx === currentIndex
            ? 'border-emerald-500 text-emerald-300'
            : idx < currentIndex
              ? 'border-slate-600 text-slate-500'
              : 'border-slate-700 text-slate-400'
        "
      >
        <span class="text-xs">{{ idx + 1 }}.</span>
        {{ step.title }}
      </li>
    </ol>

    <div class="border border-slate-800 rounded p-4 min-h-32">
      <!--
        Parent renders the body for the active step via a scoped slot.
        Keeps the wizard component generic — V1 stub and the final
        wizard feature set share the same harness without coupling to
        any one step's specific UI.
      -->
      <slot :index="currentIndex" :step="steps[currentIndex]" />
    </div>

    <div class="flex gap-2">
      <button
        type="button"
        :disabled="isFirst"
        class="px-3 py-1 rounded border border-slate-700 text-sm disabled:opacity-40 hover:bg-slate-800"
        @click="back"
      >
        Back
      </button>
      <button
        v-if="!isLast"
        type="button"
        class="px-3 py-1 rounded border border-emerald-700 bg-emerald-700/20 text-emerald-200 text-sm hover:bg-emerald-700/40"
        @click="next"
      >
        Continue
      </button>
    </div>
  </div>
</template>
