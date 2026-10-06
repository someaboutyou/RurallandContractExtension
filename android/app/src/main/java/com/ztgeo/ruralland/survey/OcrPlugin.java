package com.ztgeo.ruralland.survey;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Base64;
import com.benjaminwan.ocrlibrary.OcrEngine;
import com.benjaminwan.ocrlibrary.OcrResult;
import com.benjaminwan.ocrlibrary.Point;
import com.benjaminwan.ocrlibrary.TextBlock;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.List;

/**
 * 端侧证件 OCR 插件（仅 Android 原生壳内可用）。
 *
 * 引擎：RapidOcrAndroidOnnx 1.3.0（PP-OCRv3 det/cls/rec ONNX 模型 + onnxruntime，
 * 模型随 AAR assets 打包，{@link OcrEngine} 构造时经 AssetManager 直读）。
 *
 * 设计要点：
 * - 引擎单例 + 懒加载：首次调用加载模型（约 0.5~1s），之后常驻内存（约 80MB）；
 * - 输入用 base64：照片在 JS 侧已经过相机压缩（长边 1920），桥接传字节比解析
 *   webPath/filePath 的各种 scheme 映射可靠得多；
 * - detect 是 CPU 重活，必须在后台线程跑，结果回主线程 resolve；
 * - 本插件只输出「文字行 + 置信度 + 坐标」——字段抽取/校验全部放在 JS 层
 *   （frontend/src/mobile/ocr/parser.js），规则可随热更迭代，原生层冻结。
 */
@CapacitorPlugin(name = "Ocr")
public class OcrPlugin extends Plugin {

    private static final Object ENGINE_LOCK = new Object();
    private static final int DEFAULT_MAX_SIDE_LEN = 1600;

    private OcrEngine engine;
    private String engineError;

    private OcrEngine obtainEngine() throws IllegalStateException {
        synchronized (ENGINE_LOCK) {
            if (engine != null) {
                return engine;
            }
            try {
                // OcrEngine 构造函数内部 loadLibrary("RapidOcr") 并从 assets 加载 4 个模型文件；
                // 任一失败会抛 IllegalArgumentException。
                engine = new OcrEngine(getContext());
                return engine;
            } catch (Throwable error) {
                engineError = error == null ? "unknown" : String.valueOf(error);
                throw new IllegalStateException("OCR 引擎初始化失败: " + engineError, error);
            }
        }
    }

    @PluginMethod
    public void recognize(PluginCall call) {
        final String base64 = call.getString("imageBase64", "");
        if (base64.isEmpty()) {
            call.reject("缺少 imageBase64");
            return;
        }
        final int maxSideLen = call.getInt("maxSideLen", DEFAULT_MAX_SIDE_LEN);

        // 模型加载 + 推理都是重活；引擎初始化放锁内，推理放锁外（detect 线程安全性
        // 由"同一引擎串行调用"保证——这里用引擎级对象锁把 detect 串行化）。
        new Thread(() -> {
            try {
                OcrEngine ocrEngine = obtainEngine();
                Bitmap bitmap = decodeScaled(base64, maxSideLen);
                if (bitmap == null) {
                    call.reject("图片解码失败");
                    return;
                }
                JSObject response = runDetect(ocrEngine, bitmap, maxSideLen);
                bitmap.recycle();
                call.resolve(response);
            } catch (Exception error) {
                call.reject(error.getMessage() == null ? "识别失败" : error.getMessage());
            }
        }, "ocr-recognize").start();
    }

    /** 解码 base64 图片，并按 inSampleSize 预缩（避免 12MP 原图一次性占 48MB 内存）。 */
    private Bitmap decodeScaled(String base64, int maxSideLen) {
        byte[] bytes;
        try {
            bytes = Base64.decode(base64, Base64.DEFAULT);
        } catch (IllegalArgumentException error) {
            return null;
        }

        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            return null;
        }

        // 目标：解出来后长边约 2×maxSideLen（det 内部还会按 maxSideLen 再缩一次，
        // 这里只负责控内存），按 2 的幂取 inSampleSize。
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = 1;
        int longSide = Math.max(bounds.outWidth, bounds.outHeight);
        while (longSide / (options.inSampleSize * 2) >= maxSideLen * 2) {
            options.inSampleSize *= 2;
        }
        options.inPreferredConfig = Bitmap.Config.RGB_565; // OCR 不需要 alpha，省一半内存
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    }

    private JSObject runDetect(OcrEngine ocrEngine, Bitmap bitmap, int maxSideLen) {
        long startMs = System.currentTimeMillis();
        // output bitmap 仅用于回绘检测框，本插件不消费绘制结果，给最小尺寸即可
        Bitmap output = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888);
        OcrResult result;
        synchronized (ENGINE_LOCK) {
            result = ocrEngine.detect(
                    bitmap, output,
                    50,          // padding
                    maxSideLen,
                    0.5f,        // boxScoreThresh
                    0.3f,        // boxThresh
                    1.6f,        // unClipRatio
                    true,        // doAngle：单行文本可能倒置（拍照手持）
                    true         // mostAngle：整体角度分类
            );
        }

        JSObject response = new JSObject();
        JSArray lines = new JSArray();
        List<TextBlock> blocks = result.getTextBlocks();
        if (blocks != null) {
            for (TextBlock block : blocks) {
                JSObject line = new JSObject();
                line.put("text", block.getText());
                line.put("score", block.getBoxScore());
                JSArray box = new JSArray();
                if (block.getBoxPoint() != null) {
                    for (Point point : block.getBoxPoint()) {
                        JSObject pt = new JSObject();
                        pt.put("x", point.getX());
                        pt.put("y", point.getY());
                        box.put(pt);
                    }
                }
                line.put("box", box);
                lines.put(line);
            }
        }
        response.put("lines", lines);
        response.put("text", result.getStrRes() == null ? "" : result.getStrRes());
        response.put("elapsedMs", System.currentTimeMillis() - startMs);
        response.put("imageWidth", bitmap.getWidth());
        response.put("imageHeight", bitmap.getHeight());
        return response;
    }
}
