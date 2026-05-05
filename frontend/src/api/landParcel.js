import http from "./http";

export function fetchContractorParcels(contractorCode) {
  return http.get(`/contractors/${contractorCode}/parcels`);
}
