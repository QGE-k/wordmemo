package com.wordmemo.app

import android.annotation.SuppressLint
import android.content.Intent
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
import java.util.Locale

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private lateinit var webView: WebView
    private lateinit var loadingView: LinearLayout
    private lateinit var errorView: LinearLayout
    private var tts: TextToSpeech? = null
    private var ttsReady = false

    private val appUrl = "https://wordmemo-bbpn.onrender.com/"
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null

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

        // ===== 加载页 - 居中布局防止偏移 =====
        loadingView = LinearLayout(this)
        loadingView.orientation = LinearLayout.VERTICAL
        loadingView.gravity = Gravity.CENTER_HORIZONTAL or Gravity.CENTER_VERTICAL
        loadingView.layoutParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )
        loadingView.setBackgroundColor(Color.parseColor("#4f46e5"))

        // 应用标题
        val appName = TextView(this)
        appName.text = "背单词"
        appName.setTextColor(Color.WHITE)
        appName.textSize = 36f
        appName.typeface = android.graphics.Typeface.create(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
        appName.setPadding(0, 0, 0, 16)

        // 副标题
        val subtitle = TextView(this)
        subtitle.text = "WordMemo"
        subtitle.setTextColor(Color.parseColor("#A5B4FC"))
        subtitle.textSize = 14f
        subtitle.letterSpacing = 0.2f
        subtitle.setPadding(0, 0, 0, 40)

        // 圆形进度条 - 固定大小 + 居中
        val progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleLarge)
        val sizeInPx = (36 * resources.displayMetrics.density).toInt()
        val pbParams = LinearLayout.LayoutParams(sizeInPx, sizeInPx)
        pbParams.gravity = Gravity.CENTER_HORIZONTAL
        progressBar.layoutParams = pbParams
        progressBar.indeterminateTintList = android.content.res.ColorStateList.valueOf(Color.parseColor("#A5B4FC"))

        // 加载文字
        val loadingText = TextView(this)
        loadingText.text = "正在加载..."
        loadingText.setTextColor(Color.parseColor("#A5B4FC"))
        loadingText.textSize = 13f
        val ltParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        )
        ltParams.gravity = Gravity.CENTER_HORIZONTAL
        ltParams.topMargin = (16 * resources.displayMetrics.density).toInt()
        loadingText.layoutParams = ltParams

        loadingView.addView(appName)
        loadingView.addView(subtitle)
        loadingView.addView(progressBar)
        loadingView.addView(loadingText)

        // ===== 错误页 =====
        errorView = LinearLayout(this)
        errorView.orientation = LinearLayout.VERTICAL
        errorView.gravity = Gravity.CENTER
        errorView.layoutParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )
        errorView.setBackgroundColor(Color.parseColor("#f8fafc"))
        errorView.visibility = View.GONE

        val errorIcon = TextView(this)
        errorIcon.text = "📡"
        errorIcon.textSize = 48f

        val errorTitle = TextView(this)
        errorTitle.text = "网络连接失败"
        errorTitle.setTextColor(Color.parseColor("#1e293b"))
        errorTitle.textSize = 18f
        errorTitle.setPadding(0, 16, 0, 8)

        val errorDesc = TextView(this)
        errorDesc.text = "请检查网络连接后点击重试"
        errorDesc.setTextColor(Color.parseColor("#64748b"))
        errorDesc.textSize = 14f

        val retryBtn = Button(this)
        retryBtn.text = "重新加载"
        retryBtn.setBackgroundColor(Color.parseColor("#4f46e5"))
        retryBtn.setTextColor(Color.WHITE)
        retryBtn.setOnClickListener { loadApp() }

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
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = true
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.userAgentString = settings.userAgentString + " WordMemoApp/1.0"

        // ===== 禁用浏览器特征，让 WebView 更像原生应用 =====
        webView.isVerticalScrollBarEnabled = false
        webView.isHorizontalScrollBarEnabled = false
        webView.isScrollbarFadingEnabled = true
        webView.setOnLongClickListener { true }
        webView.isLongClickable = false
        webView.isHapticFeedbackEnabled = false

        // 添加原生 TTS 接口供 JavaScript 调用
        webView.addJavascriptInterface(TTSBridge(), "AndroidTTS")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                // 注入CSS隐藏登录表单，防止未登录时闪烁
                view?.evaluateJavascript(
                    """(function(){
                        var style = document.createElement('style');
                        style.textContent = '#loginModal{display:none!important;}';
                        document.head.appendChild(style);
                    })();""", null
                )
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
                if (newProgress >= 80) {
                    loadingView.visibility = View.GONE
                }
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback

                // 创建可拍照 + 选图的选择器
                val intent = Intent(Intent.ACTION_CHOOSER)

                // 拍照 Intent
                val cameraIntent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)

                // 选图 Intent
                val galleryIntent = Intent(Intent.ACTION_GET_CONTENT)
                galleryIntent.type = "image/*"
                galleryIntent.addCategory(Intent.CATEGORY_OPENABLE)

                // 合并 Intent
                val intentArray = arrayOf(cameraIntent)
                intent.putExtra(Intent.EXTRA_INTENT, galleryIntent)
                intent.putExtra(Intent.EXTRA_INITIAL_INTENTS, intentArray)
                intent.putExtra(Intent.EXTRA_TITLE, "拍照或选择图片")

                try {
                    @Suppress("DEPRECATION")
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST)
                } catch (e: Exception) {
                    fileChooserCallback = null
                    return false
                }
                return true
            }
        }
    }

    private fun loadApp() {
        errorView.visibility = View.GONE
        loadingView.visibility = View.VISIBLE
        webView.loadUrl(appUrl)
    }

    // ===== TTS 初始化回调 =====
    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            val result = tts?.setLanguage(Locale.US)
            ttsReady = result != TextToSpeech.LANG_MISSING_DATA &&
                       result != TextToSpeech.LANG_NOT_SUPPORTED
        }
    }

    // ===== TTS 接口 - 供 JavaScript 调用 =====
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
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == FILE_CHOOSER_REQUEST) {
            val results: Array<Uri>? = if (resultCode == RESULT_OK) {
                val uri = data?.data
                if (uri != null) arrayOf(uri) else null
            } else {
                null
            }
            fileChooserCallback?.onReceiveValue(results)
            fileChooserCallback = null
        }
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

    companion object {
        private const val FILE_CHOOSER_REQUEST = 10001
    }
}
