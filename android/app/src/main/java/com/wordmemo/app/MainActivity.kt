package com.wordmemo.app

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * 主界面：全屏 WebView 加载背单词应用
 *
 * 与浏览器的区别：
 * - 没有地址栏、标签栏、导航按钮
 * - 全屏沉浸式体验
 * - 物理返回键控制网页后退（不退出App）
 * - 下拉刷新
 * - 网络断开时显示原生错误页
 * - 支持文件上传（拍照录入）
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var loadingView: LinearLayout
    private lateinit var errorView: LinearLayout
    private lateinit var progressBar: ProgressBar

    // App 部署地址（云服务）
    private val appUrl = "https://wordmemo-bbpn.onrender.com/"

    // 文件上传回调
    private var fileChooserCallback: android.webkit.ValueCallback<Array<android.net.Uri>>? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 全屏沉浸式
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        )
        window.statusBarColor = Color.parseColor("#4f46e5")

        // 创建根布局
        val rootLayout = FrameLayout(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(Color.parseColor("#f8fafc"))
        }

        // SwipeRefreshLayout 包裹 WebView
        swipeRefresh = SwipeRefreshLayout(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            setOnRefreshListener {
                webView.reload()
            }
            setColorSchemeColors(
                Color.parseColor("#4f46e5"),
                Color.parseColor("#6366f1")
            )
        }

        // WebView
        webView = WebView(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            id = View.generateViewId()
        }
        swipeRefresh.addView(webView)

        // 加载中视图
        loadingView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = android.view.Gravity.CENTER
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(Color.parseColor("#f8fafc"))
            visibility = View.VISIBLE
        }
        progressBar = ProgressBar(this).apply {
            isIndeterminate = true
            progressTintList = android.content.res.ColorStateList.valueOf(Color.parseColor("#4f46e5"))
        }
        val loadingText = TextView(this).apply {
            text = "正在加载..."
            setTextColor(Color.parseColor("#64748b"))
            textSize = 14f
            setPadding(0, 24, 0, 0)
        }
        loadingView.addView(progressBar)
        loadingView.addView(loadingText)

        // 错误页（网络断开时显示）
        errorView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = android.view.Gravity.CENTER
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
        }
        val errorTitle = TextView(this).apply {
            text = "网络连接失败"
            setTextColor(Color.parseColor("#1e293b"))
            textSize = 18f
            setPadding(0, 16, 0, 8)
        }
        val errorDesc = TextView(this).apply {
            text = "请检查网络连接后点击重试"
            setTextColor(Color.parseColor("#64748b"))
            textSize = 14f
        }
        val retryBtn = android.widget.Button(this).apply {
            text = "重新加载"
            setBackgroundColor(Color.parseColor("#4f46e5"))
            setTextColor(Color.WHITE)
            setOnClickListener { loadApp() }
            setPadding(48, 24, 48, 24)
        }
        errorView.addView(errorIcon)
        errorView.addView(errorTitle)
        errorView.addView(errorDesc)
        errorView.addView(retryBtn)

        rootLayout.addView(swipeRefresh)
        rootLayout.addView(loadingView)
        rootLayout.addView(errorView)
        setContentView(rootLayout)

        // 配置 WebView
        configureWebView()

        // 加载应用
        loadApp()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true          // localStorage 支持
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            allowFileAccess = true
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            userAgentString = "$userAgentString WordMemoApp/1.0"
            // 支持缩放
            setSupportZoom(false)
            builtInZoomControls = false
            // 自适应屏幕
            useWideViewPort = true
            loadWithOverviewMode = true
            // 支持文件上传
            javaScriptCanOpenWindowsAutomatically = true
        }

        // WebViewClient：页面内跳转，不打开外部浏览器
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                loadingView.visibility = View.GONE
                swipeRefresh.isRefreshing = false
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    loadingView.visibility = View.GONE
                    swipeRefresh.isRefreshing = false
                    errorView.visibility = View.VISIBLE
                }
            }
        }

        // WebChromeClient：支持文件选择（扫描录入）和进度
        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                if (newProgress >= 80) {
                    loadingView.visibility = View.GONE
                }
            }

            // 文件上传支持（扫描录入功能）
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: android.webkit.ValueCallback<Array<android.net.Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                try {
                    val intent = fileChooserParams?.createIntent()
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

    /**
     * 物理返回键：先网页后退，退到底了再退出App
     */
    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: android.content.Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == FILE_CHOOSER_REQUEST) {
            val result = if (resultCode == RESULT_OK && data != null) {
                arrayOf(android.net.Uri.parse(data.dataString))
            } else {
                null
            }
            fileChooserCallback?.onReceiveValue(result)
            fileChooserCallback = null
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        webView.apply {
            loadUrl("about:blank")
            clearHistory()
            parent?.let { (it as? FrameLayout)?.removeView(this) }
            destroy()
        }
    }

    companion object {
        private const val FILE_CHOOSER_REQUEST = 10001
    }
}
