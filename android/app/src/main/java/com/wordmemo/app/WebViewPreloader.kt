package com.wordmemo.app

import android.content.Context
import android.webkit.WebView

/**
 * WebView 预热器
 *
 * 首次创建 WebView 时，系统需要启动独立的渲染进程（约 200~500ms）。
 * 在 Splash 页面期间提前创建一个 WebView 并持有引用，
 * 让渲染进程在后台预启动，这样 MainActivity 创建 WebView 时即可秒开，
 * 显著缩短冷启动加载时间。
 *
 * 注意：持有引用不销毁，避免渲染进程被回收。
 */
object WebViewPreloader {

    @Volatile
    private var preloaded = false

    // 持有 WebView 引用，防止渲染进程被回收
    private var holder: WebView? = null

    /**
     * 预热 WebView 渲染进程（幂等，可安全重复调用）
     */
    fun preload(context: Context) {
        if (preloaded) return
        synchronized(this) {
            if (preloaded) return
            try {
                holder = WebView(context.applicationContext).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                }
                preloaded = true
            } catch (_: Exception) {
                // 预热失败不影响正常使用
                preloaded = true
            }
        }
    }
}