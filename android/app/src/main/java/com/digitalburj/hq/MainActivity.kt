package com.digitalburj.hq

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.Network
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.Toast
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/**
 * DigitalBurj HQ: a hardened WebView shell around https://hq.digitalburj.com.
 *
 * - Only the HQ origin loads inside the app; every other link opens in the user's browser or mail/phone app.
 * - No JavaScript bridge is exposed, file and content access are disabled, and cleartext traffic is blocked.
 * - Uploads use the system picker (camera, gallery, files); downloads go through the system DownloadManager.
 * - Offline or unreachable: a local page is shown and the app reconnects by itself when the network returns.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var progress: ProgressBar
    private lateinit var scrim: View
    private val main = Handler(Looper.getMainLooper())
    private var splashDone = false
    private var uploadCallback: ValueCallback<Array<Uri>>? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    private val picker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        uploadCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data))
        uploadCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        splash.setKeepOnScreenCondition { !splashDone }
        main.postDelayed({ splashDone = true }, SPLASH_MAX_MS)

        if (BuildConfig.SECURE_SCREEN) {
            // Keeps private documents out of screenshots and the recent-apps thumbnail.
            window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        }
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(ContextCompat.getColor(this, R.color.ink)),
            navigationBarStyle = SystemBarStyle.light(
                ContextCompat.getColor(this, R.color.paper),
                ContextCompat.getColor(this, R.color.paper),
            ),
        )
        setContentView(R.layout.activity_main)

        web = findViewById(R.id.web)
        progress = findViewById(R.id.progress)
        scrim = findViewById(R.id.scrim)
        applyInsets()
        configureWebView()

        onBackPressedDispatcher.addCallback(this, object : androidx.activity.OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val self = this
                web.evaluateJavascript(BACK_JS) { handled ->
                    when {
                        handled == "true" -> Unit
                        web.url == OFFLINE_URL -> finish()
                        web.canGoBack() -> web.goBack()
                        else -> {
                            self.isEnabled = false
                            onBackPressedDispatcher.onBackPressed()
                        }
                    }
                }
            }
        })

        val restored = savedInstanceState?.let { web.restoreState(it) } != null
        if (!restored) web.loadUrl(deepLink(intent) ?: BuildConfig.HQ_URL)
    }

    private fun applyInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root)) { _, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            scrim.layoutParams = scrim.layoutParams.apply { height = bars.top }
            progress.layoutParams = (progress.layoutParams as FrameLayout.LayoutParams).apply { topMargin = bars.top }
            web.layoutParams = (web.layoutParams as FrameLayout.LayoutParams).apply {
                setMargins(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
            }
            WindowInsetsCompat.CONSUMED
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = true
            setSupportZoom(false)
            builtInZoomControls = false
            textZoom = 100
            safeBrowsingEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            userAgentString = "$userAgentString DigitalBurjHQ-Android/${BuildConfig.VERSION_NAME}"
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(web, false)
        }

        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (!request.isForMainFrame) return false
                val target = request.url
                if (isHome(target) || target.toString() == OFFLINE_URL) return false
                openExternally(target)
                return true
            }

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                progress.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView, url: String?) {
                progress.visibility = View.GONE
                splashDone = true
                CookieManager.getInstance().flush()
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame && request.url.toString() != OFFLINE_URL) view.loadUrl(OFFLINE_URL)
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                // The renderer was killed (memory pressure or crash): rebuild the whole activity.
                recreate()
                return true
            }
        }

        web.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progress.progress = newProgress
                if (newProgress >= 70) splashDone = true
            }

            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams,
            ): Boolean {
                uploadCallback?.onReceiveValue(null)
                uploadCallback = filePathCallback
                return try {
                    picker.launch(fileChooserParams.createIntent())
                    true
                } catch (_: ActivityNotFoundException) {
                    uploadCallback = null
                    false
                }
            }
        }

        web.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            val uri = Uri.parse(url)
            if (uri.scheme != "https") return@setDownloadListener
            val request = DownloadManager.Request(uri)
                .setMimeType(mimeType)
                .addRequestHeader("User-Agent", userAgent)
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalPublicDir(
                    Environment.DIRECTORY_DOWNLOADS,
                    URLUtil.guessFileName(url, contentDisposition, mimeType),
                )
            // Session cookies go only to HQ itself, never to the storage host a download redirects to.
            if (isHome(uri)) CookieManager.getInstance().getCookie(url)?.let { request.addRequestHeader("Cookie", it) }
            (getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
            Toast.makeText(this, R.string.downloading, Toast.LENGTH_SHORT).show()
        }
    }

    private fun isHome(uri: Uri) = uri.scheme == "https" && uri.host == BuildConfig.HQ_HOST

    private fun deepLink(intent: Intent?): String? =
        intent?.data?.takeIf { isHome(it) }?.toString()

    private fun openExternally(uri: Uri) {
        if (uri.scheme !in EXTERNAL_SCHEMES) return
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE))
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(this, R.string.no_app_for_link, Toast.LENGTH_SHORT).show()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        deepLink(intent)?.let { web.loadUrl(it) }
    }

    override fun onStart() {
        super.onStart()
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                main.post { if (web.url == OFFLINE_URL) web.loadUrl(BuildConfig.HQ_URL) }
            }
        }
        networkCallback = callback
        manager.registerDefaultNetworkCallback(callback)
    }

    override fun onStop() {
        networkCallback?.let { (getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager).unregisterNetworkCallback(it) }
        networkCallback = null
        CookieManager.getInstance().flush()
        super.onStop()
    }

    override fun onResume() {
        super.onResume()
        web.onResume()
    }

    override fun onPause() {
        web.onPause()
        super.onPause()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        uploadCallback?.onReceiveValue(null)
        uploadCallback = null
        (web.parent as? android.view.ViewGroup)?.removeView(web)
        web.destroy()
        super.onDestroy()
    }

    private companion object {
        const val OFFLINE_URL = "file:///android_asset/offline.html"
        const val SPLASH_MAX_MS = 3500L
        val EXTERNAL_SCHEMES = setOf("https", "http", "mailto", "tel")
        const val BACK_JS = "(function(){try{return !!(window.hqBack&&window.hqBack())}catch(e){return false}})()"
    }
}
