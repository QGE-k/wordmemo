package com.wordmemo.app

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
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

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var loadingView: LinearLayout
    private lateinit var errorView: LinearLayout

    private val appUrl = "https://wordmemo-bbpn.onrender.com/"
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.statusBarColor = Color.parseColor("#4f46e5")

        val root = FrameLayout(this)
        root.layoutParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )
        root.setBackgroundColor(Color.parseColor("#f8fafc"))

        // WebView
        webView = WebView(this)
        webView.layoutParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )

        // Loading view
        loadingView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(Color.parseColor("#f8fafc"))
        }
        val progressBar = ProgressBar(this)
        val loadingText = TextView(this).apply {
            text = "正在加载..."
            setTextColor(Color.parseColor("#64748b"))
            textSize = 14f
            setPadding(0, 24, 0, 0)
        }
        loadingView.addView(progressBar)
        loadingView.addView(loadingText)

        // Error view
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
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            allowFileAccess = true
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            useWideViewPort = true
            loadWithOverviewMode = true
            javaScriptCanOpenWindowsAutomatically = true
            userAgentString = userAgentString + " WordMemoApp/1.0"
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
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
                try {
                    val intent = fileChooserParams?.createIntent()
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
        webView.loadUrl("about:blank")
        webView.clearHistory()
        webView.destroy()
        super.onDestroy()
    }

    companion object {
        private const val FILE_CHOOSER_REQUEST = 10001
    }
}
