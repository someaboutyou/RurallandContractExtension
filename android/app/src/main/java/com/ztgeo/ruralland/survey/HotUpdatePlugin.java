package com.ztgeo.ruralland.survey;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.File;

/**
 * Web 资源热更：JS 侧切换加载目录的通道。
 *
 * Capacitor 7 没有暴露 JS 可调的 WebView 插件（setServerBasePath 只在原生
 * com.getcapacitor.Bridge 上），这里用 20 行插件把该能力转给 JS：
 *
 * - apply({path: "<绝对目录>"}) → 从该目录加载（要求目录下有 index.html），
 *   bridge.setServerBasePath 会立即重载 WebView；
 * - apply({path: ""})          → 回到 APK 内置资源（setServerAssetPath("public")）。
 *
 * 配套的冷启动激活逻辑在 MainActivity.load()：读 filesDir/bundles/current.json。
 * 指针文件由 JS（frontend/src/mobile/updater.js）下载完成后写入。
 */
@CapacitorPlugin(name = "HotUpdate")
public class HotUpdatePlugin extends Plugin {

    @PluginMethod
    public void apply(PluginCall call) {
        String path = call.getString("path", "");
        if (path == null || path.trim().isEmpty()) {
            getBridge().setServerAssetPath("public");
            call.resolve();
            return;
        }

        File dir = new File(path);
        if (!dir.isDirectory() || !new File(dir, "index.html").isFile()) {
            call.reject("invalid bundle path: " + path);
            return;
        }

        getBridge().setServerBasePath(path);
        call.resolve();
    }
}
