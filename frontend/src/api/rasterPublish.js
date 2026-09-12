import http from "./http";

/** 验证tif文件是否存在 */
export function validateTif(tifPath) {
  return http.post("/raster-publish/validate-tif", { tif_path: tifPath });
}

/** 上传shp压缩包 */
export function uploadShp(file) {
  const formData = new FormData();
  formData.append("file", file);
  return http.post("/raster-publish/upload-shp", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

/** 启动发布任务 */
export function publishRaster(payload) {
  return http.post("/raster-publish/publish", payload);
}

/** 查询任务进度 */
export function getPublishProgress(taskId) {
  return http.get(`/raster-publish/progress/${taskId}`);
}
