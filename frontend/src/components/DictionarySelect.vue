<template>
  <el-select
    :model-value="modelValue"
    :loading="loading"
    :clearable="clearable"
    :filterable="filterable"
    :placeholder="placeholder"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-option v-for="item in options" :key="item.value" :label="item.label" :value="item.value" />
  </el-select>
</template>

<script setup>
import { useDictionary } from "../composables/useDictionary";

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean],
    default: "",
  },
  dictType: {
    type: String,
    required: true,
  },
  placeholder: {
    type: String,
    default: "请选择",
  },
  clearable: {
    type: Boolean,
    default: true,
  },
  filterable: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["update:modelValue"]);

const { options, loading } = useDictionary(props.dictType);
</script>
