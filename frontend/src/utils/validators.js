export const MOBILE_REGEX = /^1[3-9]\d{9}$/;
export const CHINA_ID_REGEX = /(^\d{15}$)|(^\d{17}[\dXx]$)/;
export const POSTCODE_REGEX = /^\d{6}$/;

export function validateMobile(value) {
  return MOBILE_REGEX.test(String(value).trim());
}

export function validateChinaId(value) {
  return CHINA_ID_REGEX.test(String(value).trim());
}

export function validatePostcode(value) {
  return POSTCODE_REGEX.test(String(value).trim());
}
