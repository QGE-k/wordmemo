package com.wordmemo.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.speech.tts.TextToSpeech
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.ValueCallback
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private lateinit var webView: WebView
    private lateinit var loadingView: LinearLayout
    private lateinit var errorView: LinearLayout
    private var tts: TextToSpeech? = null
    private var ttsReady = false

    private val appUrl = "https://wordmemo-bbpn.onrender.com/"
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var cameraImageUri: Uri? = null
    private var backPressedTime: Long = 0

    companion object {
        private const val FILE_CHOOSER_REQUEST = 10001
        private const val CAMERA_PERMISSION_REQUEST = 10002
        private const val REQUEST_CAMERA_ONLY = 10003
        private const val REQUEST_GALLERY_ONLY = 10004
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 初始化原生 TTS 引擎
        tts = TextToSpeech(this, this)

        window.statusBarColor = Color.parseColor("#4f46e5")

        val root = FrameLayout(this)
        root.layoutParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )

        webView = WebView(this)
        webView.layoutParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )

        // ===== 加载页 - 居中布局 =====
        loadingView = LinearLayout(this)
        loadingView.orientation = LinearLayout.VERTICAL
        loadingView.gravity = Gravity.CENTER
        val loadingParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )
        loadingView.layoutParams = loadingParams
        loadingView.setBackgroundColor(Color.parseColor("#4f46e5"))

        val appName = TextView(this).apply {
            text = "背单词"
            setTextColor(Color.WHITE)
            textSize = 36f
            typeface = android.graphics.Typeface.create(
                android.graphics.Typeface.DEFAULT,
                android.graphics.Typeface.BOLD
            )
            gravity = Gravity.CENTER
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.gravity = Gravity.CENTER
            layoutParams = lp
            setPadding(0, 0, 0, 16)
        }

        val subtitle = TextView(this).apply {
            text = "WordMemo"
            setTextColor(Color.parseColor("#A5B4FC"))
            textSize = 14f
            letterSpacing = 0.2f
            gravity = Gravity.CENTER
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.gravity = Gravity.CENTER
            layoutParams = lp
            setPadding(0, 0, 0, 48)
        }

        val progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleLarge).apply {
            val sizeInPx = (36 * resources.displayMetrics.density).toInt()
            val lp = LinearLayout.LayoutParams(sizeInPx, sizeInPx)
            lp.gravity = Gravity.CENTER
            layoutParams = lp
            indeterminateTintList = android.content.res.ColorStateList.valueOf(
                Color.parseColor("#A5B4FC")
            )
        }

        val loadingText = TextView(this).apply {
            text = "正在加载..."
            setTextColor(Color.parseColor("#A5B4FC"))
            textSize = 13f
            gravity = Gravity.CENTER
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.gravity = Gravity.CENTER
            lp.topMargin = (16 * resources.displayMetrics.density).toInt()
            layoutParams = lp
        }

        loadingView.addView(appName)
        loadingView.addView(subtitle)
        loadingView.addView(progressBar)
        loadingView.addView(loadingText)

        // ===== 错误页 =====
        errorView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(Color.parseColor("#f8fafc"))
            visibility = View.GONE
        }

        val errorIcon = TextView(this).apply {
            text = "📡"
            textSize = 48f
            gravity = Gravity.CENTER
        }
        val errorTitle = TextView(this).apply {
            text = "网络连接失败"
            setTextColor(Color.parseColor("#1e293b"))
            textSize = 18f
            gravity = Gravity.CENTER
            setPadding(0, 16, 0, 8)
        }
        val errorDesc = TextView(this).apply {
            text = "请检查网络连接后点击重试"
            setTextColor(Color.parseColor("#64748b"))
            textSize = 14f
            gravity = Gravity.CENTER
        }
        val retryBtn = Button(this).apply {
            text = "重新加载"
            setBackgroundColor(Color.parseColor("#4f46e5"))
            setTextColor(Color.WHITE)
            setOnClickListener { loadApp() }
        }

        errorView.addView(errorIcon)
        errorView.addView(errorTitle)
        errorView.addView(errorDesc)
        errorView.addView(retryBtn)

        root.addView(webView)
        root.addView(loadingView)
        root.addView(errorView)
        setContentView(root)

        setupWebView()
        loadApp()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        // 缓存策略：LOAD_DEFAULT 让 Service Worker 控制缓存
        // SW 的 stale-while-revalidate 策略：先返回缓存秒开，后台更新最新版本
        // 避免 LOAD_CACHE_ELSE_NETWORK 导致前端更新后 WebView 仍用旧缓存
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        // setAppCacheEnabled 已在 API 34 移除，使用 domStorage 替代
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        // 关闭 wideViewPort 和 overviewMode，防止触发桌面端 CSS 媒体查询导致标题偏移
        settings.useWideViewPort = false
        settings.loadWithOverviewMode = false
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.userAgentString = settings.userAgentString + " WordMemoApp/1.0"

        // ===== 禁用浏览器特征 =====
        webView.isVerticalScrollBarEnabled = false
        webView.isHorizontalScrollBarEnabled = false
        webView.isScrollbarFadingEnabled = true
        webView.setOnLongClickListener { true }
        webView.isLongClickable = false
        webView.isHapticFeedbackEnabled = false

        // 添加原生 TTS 接口
        webView.addJavascriptInterface(TTSBridge(), "AndroidTTS")

        // 设置 WebView 背景为白色，避免加载时出现黑底闪烁
        webView.setBackgroundColor(Color.WHITE)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageCommitVisible(view: WebView?, url: String?) {
                super.onPageCommitVisible(view, url)
                // 页面内容可见时才隐藏加载页，避免白屏闪烁
                loadingView.visibility = View.GONE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                // 注入 CSS 强制移动端布局，防止桌面端媒体查询导致标题偏移
                view?.evaluateJavascript(
                    """(function(){
                        var style = document.createElement('style');
                        style.textContent = '@media (min-width:768px){.status-bar{left:0!important;right:0!important;max-width:480px!important;margin:0 auto!important;}}';
                        document.head.appendChild(style);
                    })();""", null
                )
                // 确保加载页已隐藏
                loadingView.visibility = View.GONE
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    loadingView.visibility = View.GONE
                    errorView.visibility = View.VISIBLE
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                // 页面加载到 80% 才隐藏加载页，确保内容已渲染（避免看到空白页闪烁）
                if (newProgress >= 80) {
                    loadingView.visibility = View.GONE
                }
            }

            // 支持 JS confirm() 对话框，避免 WebView 中 confirm 不弹窗导致逻辑卡死
            override fun onJsConfirm(
                view: WebView?, url: String?, message: String?, result: android.webkit.JsResult?
            ): Boolean {
                AlertDialog.Builder(this@MainActivity)
                    .setMessage(message ?: "")
                    .setPositiveButton("确定") { _, _ -> result?.confirm() }
                    .setNegativeButton("取消") { _, _ -> result?.cancel() }
                    .setOnCancelListener { result?.cancel() }
                    .show()
                return true
            }

            // 支持 JS alert() 对话框
            override fun onJsAlert(
                view: WebView?, url: String?, message: String?, result: android.webkit.JsResult?
            ): Boolean {
                AlertDialog.Builder(this@MainActivity)
                    .setMessage(message ?: "")
                    .setPositiveButton("确定") { _, _ -> result?.confirm() }
                    .setOnCancelListener { result?.cancel() }
                    .show()
                return true
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback

                // 弹出选择框：拍照 / 从相册选择
                val dialog = AlertDialog.Builder(this@MainActivity)
                    .setTitle("选择图片")
                    .setItems(arrayOf("📷 拍照", "🖼️ 从相册选择")) { _, which ->
                        when (which) {
                            0 -> startCamera()
                            1 -> startGallery()
                        }
                    }
                    .setOnCancelListener {
                        fileChooserCallback?.onReceiveValue(null)
                        fileChooserCallback = null
                    }
                    .create()
                dialog.show()
                return true
            }
        }
    }

    /**
     * 启动相机拍照
     * 需要 CAMERA 运行时权限
     */
    private fun startCamera() {
        // 检查相机权限
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            // 请求权限
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.CAMERA),
                CAMERA_PERMISSION_REQUEST
            )
        } else {
            launchCameraIntent()
        }
    }

    /**
     * 创建临时文件并启动相机 Intent
     */
    private fun launchCameraIntent() {
        try {
            // 创建临时文件存储拍照结果
            val imageDir = File(cacheDir, "images")
            if (!imageDir.exists()) imageDir.mkdirs()
            val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
            val imageFile = File(imageDir, "IMG_$timeStamp.jpg")

            // 通过 FileProvider 获取 content URI
            cameraImageUri = FileProvider.getUriForFile(
                this,
                "${packageName}.fileprovider",
                imageFile
            )

            val cameraIntent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                putExtra(MediaStore.EXTRA_OUTPUT, cameraImageUri)
                addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            }

            startActivityForResult(cameraIntent, REQUEST_CAMERA_ONLY)
        } catch (e: Exception) {
            fileChooserCallback?.onReceiveValue(null)
            fileChooserCallback = null
        }
    }

    /**
     * 启动图库选择图片
     */
    private fun startGallery() {
        val galleryIntent = Intent(Intent.ACTION_GET_CONTENT).apply {
            type = "image/*"
            addCategory(Intent.CATEGORY_OPENABLE)
        }
        startActivityForResult(galleryIntent, REQUEST_GALLERY_ONLY)
    }

    private fun loadApp() {
        errorView.visibility = View.GONE
        loadingView.visibility = View.VISIBLE
        webView.loadUrl(appUrl)
    }

    // ===== 运行时权限回调 =====
    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            CAMERA_PERMISSION_REQUEST -> {
                if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                    launchCameraIntent()
                } else {
                    // 权限被拒绝，通知 WebView
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = null
                }
            }
        }
    }

    // ===== TTS 初始化回调 =====
    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            val result = tts?.setLanguage(Locale.US)
            ttsReady = result != TextToSpeech.LANG_MISSING_DATA &&
                       result != TextToSpeech.LANG_NOT_SUPPORTED
        }
    }

    // ===== TTS 接口 =====
    inner class TTSBridge {
        @JavascriptInterface
        fun speak(text: String) {
            if (ttsReady && tts != null) {
                tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "word_$text")
            }
        }

        @JavascriptInterface
        fun isAvailable(): Boolean {
            return ttsReady
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (webView.canGoBack()) {
                webView.goBack()
                return true
            }
            // 双击退出
            val now = System.currentTimeMillis()
            if (now - backPressedTime < 2000) {
                finish()
            } else {
                backPressedTime = now
                android.widget.Toast.makeText(this, "再按一次返回键退出", android.widget.Toast.LENGTH_SHORT).show()
            }
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        var results: Array<Uri>? = null

        if (resultCode == RESULT_OK) {
            when (requestCode) {
                REQUEST_CAMERA_ONLY -> {
                    // 拍照返回：使用创建的临时文件 URI
                    results = cameraImageUri?.let { arrayOf(it) }
                }
                REQUEST_GALLERY_ONLY -> {
                    // 选图返回：使用返回的 data URI
                    results = data?.data?.let { arrayOf(it) }
                }
            }
        }

        fileChooserCallback?.onReceiveValue(results)
        fileChooserCallback = null
        cameraImageUri = null
    }

    override fun onDestroy() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        webView.loadUrl("about:blank")
        webView.clearHistory()
        webView.destroy()
        super.onDestroy()
    }
}
