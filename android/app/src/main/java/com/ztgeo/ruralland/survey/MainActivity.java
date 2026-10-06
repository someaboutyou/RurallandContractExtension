package com.ztgeo.ruralland.survey;

import android.util.Log;

import com.getcapacitor.BridgeActivity;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "HotUpdate";

    @Override
    protected void load() {
        // JS 侧回滚/兜底切换要用的插件，必须在 bridge 创建前注册
        registerPlugin(HotUpdatePlugin.class);
        // 端侧证件 OCR（RapidOcr onnx 引擎，模型随 AAR assets 打包）
        registerPlugin(OcrPlugin.class);
        super.load();
        applyHotUpdatePointer();
    }

    /**
     * 冷启动激活热更：读 filesDir/bundles/current.json（由 JS 下载完成后写入），
     * 指向的 bundle 完整可用则直接从该目录加载 —— 单次启动即新版，无需二次跳转。
     *
     * 指针缺失/损坏/目录被清 → 按内置资源启动，绝不让 App 起不来。
     */
    private void applyHotUpdatePointer() {
        try {
            File pointer = new File(getFilesDir(), "bundles/current.json");
            if (!pointer.isFile()) {
                return;
            }

            StringBuilder json = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(new FileInputStream(pointer), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    json.append(line);
                }
            }

            String path = new JSONObject(json.toString()).optString("path", "");
            if (path.isEmpty()) {
                return;
            }

            File dir = new File(path);
            if (dir.isDirectory() && new File(dir, "index.html").isFile()) {
                bridge.setServerBasePath(path);
                Log.i(TAG, "loaded bundle: " + path);
            } else {
                Log.w(TAG, "bundle dir missing index.html, fallback to builtin: " + path);
            }
        } catch (Exception ex) {
            Log.w(TAG, "apply hot-update pointer failed", ex);
        }
    }
}
