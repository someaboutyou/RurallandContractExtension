import http from "./http";

export function fetchDictionaryItems(params = {}) {
  return http.get("/dictionaries", { params });
}

export function fetchDictionaryOptions(dictType) {
  return http.get(`/dictionaries/options/${dictType}`);
}

export function createDictionaryItem(payload) {
  return http.post("/dictionaries", payload);
}

export function updateDictionaryItem(itemId, payload) {
  return http.put(`/dictionaries/${itemId}`, payload);
}

export function deleteDictionaryItem(itemId) {
  return http.delete(`/dictionaries/${itemId}`);
}
