import { computed, ref } from "vue";

import { fetchDictionaryOptions } from "../api/dictionary";

const dictionaryCache = new Map();
const pendingRequests = new Map();

async function requestDictionary(dictType, { force = false } = {}) {
  if (!dictType) {
    return [];
  }
  if (!force && dictionaryCache.has(dictType)) {
    return dictionaryCache.get(dictType);
  }
  if (!force && pendingRequests.has(dictType)) {
    return pendingRequests.get(dictType);
  }

  const request = fetchDictionaryOptions(dictType)
    .then(({ data }) => {
      const options = data.data || [];
      dictionaryCache.set(dictType, options);
      return options;
    })
    .finally(() => {
      pendingRequests.delete(dictType);
    });
  pendingRequests.set(dictType, request);
  return request;
}

export function clearDictionaryCache(dictType) {
  if (dictType) {
    dictionaryCache.delete(dictType);
    pendingRequests.delete(dictType);
    return;
  }
  dictionaryCache.clear();
  pendingRequests.clear();
}

export function useDictionary(dictType, options = {}) {
  const rows = ref(dictionaryCache.get(dictType) || []);
  const loading = ref(false);

  async function load(loadOptions = {}) {
    loading.value = true;
    try {
      rows.value = await requestDictionary(dictType, loadOptions);
      return rows.value;
    } finally {
      loading.value = false;
    }
  }

  if (options.immediate !== false) {
    load();
  }

  const labelMap = computed(() =>
    rows.value.reduce((result, item) => {
      result[item.value] = item.label;
      return result;
    }, {}),
  );

  function labelOf(value, fallback = "") {
    return labelMap.value[value] || fallback || value || "";
  }

  return {
    options: rows,
    loading,
    labelMap,
    labelOf,
    reload: () => load({ force: true }),
  };
}
