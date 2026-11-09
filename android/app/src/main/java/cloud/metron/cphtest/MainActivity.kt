package cloud.metron.cphtest

import android.app.AlertDialog
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Bundle
import android.os.SystemClock
import android.text.InputType
import android.view.View
import android.view.WindowManager
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.File
import java.util.Locale

class MainActivity : ComponentActivity() {
    private lateinit var column: LinearLayout
    private lateinit var store: ConnectionStore
    private val api=MetronApi()
    private var page="home"
    private var job: Job?=null
    private var generation=0
    private var busy=false
    private val coverFile get()=File(cacheDir,"confirmed-cover.jpg")
    private val capture=registerForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { result ->
        busy=false
        if(result.resultCode!=RESULT_OK) { imageSearch();return@registerForActivityResult }
        val uri=GmsDocumentScanningResult.fromActivityResultIntent(result.data)?.pages?.firstOrNull()?.imageUri
        if(uri==null) { imageSearch();message("No cover returned. Try again.");return@registerForActivityResult }
        job=lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) { contentResolver.openInputStream(uri)!!.use { input -> coverFile.outputStream().use { input.copyTo(it) } } }
                review()
            } catch(e:CancellationException) { throw e }
            catch(_:Exception) { imageSearch();message("Unable to read the captured cover. Try again.") }
        }
    }
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState);store=ConnectionStore(this)
        onBackPressedDispatcher.addCallback(this,object:OnBackPressedCallback(true) {
            override fun handleOnBackPressed() { if(page=="home") finish() else { busy=false;home() } }
        })
        if(savedInstanceState?.getString("page") in setOf("review","results") && coverFile.exists()) review() else home()
    }
    override fun onSaveInstanceState(outState:Bundle) { outState.putString("page",page);super.onSaveInstanceState(outState) }
    private fun dp(n:Int)=(n*resources.displayMetrics.density).toInt()
    private fun screen(name:String,title:String) {
        job?.cancel();job=null;generation++;page=name
        if(name=="configuration") window.addFlags(WindowManager.LayoutParams.FLAG_SECURE) else window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        column=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setPadding(dp(20),dp(20),dp(20),dp(20));setBackgroundColor(Color.rgb(20,25,35)) }
        val scroll=ScrollView(this).apply { isFillViewport=true;addView(column) };setContentView(scroll)
        ViewCompat.setOnApplyWindowInsetsListener(scroll) { view,insets ->
            val b=insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            view.setPadding(b.left,b.top,b.right,b.bottom);insets
        }
        ViewCompat.requestApplyInsets(scroll);label(title,26f)
    }
    private fun label(text:String,size:Float=16f):TextView = TextView(this).apply {
        this.text=text;textSize=size;setTextColor(Color.rgb(233,238,247));setPadding(0,dp(8),0,dp(8));column.addView(this)
    }
    private fun button(text:String,action:()->Unit)=Button(this).apply {
        this.text=text;isAllCaps=false;column.addView(this,LinearLayout.LayoutParams(-1,dp(56)).apply { topMargin=dp(10) });setOnClickListener { action() }
    }
    private fun message(text:String) { AlertDialog.Builder(this).setMessage(text).setPositiveButton("OK",null).show() }
    private fun home() {
        busy=false;screen("home","CPHTest")
        label("Cover Perceptual Hash Test")
        button("Configuration") { configuration() }
        button("Image Search") { imageSearch() }
    }
    private fun configuration() {
        val current=store.load();screen("configuration","Configuration")
        label("IP/Hostname of Metron Instance")
        val url=EditText(this).apply { inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI;hint="http://192.168.1.10:8000";setText(current?.url ?: "");setTextColor(Color.WHITE);setHintTextColor(Color.LTGRAY);setSingleLine();isSaveEnabled=false;column.addView(this) }
        label("Metron API Key")
        val token=EditText(this).apply { inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD;setText(current?.token ?: "");setTextColor(Color.WHITE);setSingleLine();isSaveEnabled=false;importantForAutofill=View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS;column.addView(this) }
        label("Use the server’s LAN address for a physical phone. Emulator host: http://10.0.2.2:8000.",14f)
        button("Save") {
            try {
                val normalized=InstanceUrl.normalize(url.text.toString());val key=token.text.toString().trim()
                require(key.isNotEmpty() && key.none { it=='\n' || it=='\r' }) { "Enter a Metron API key." }
                store.save(Connection(normalized,key));home()
            } catch(e:IllegalArgumentException) { message(e.message ?: "Check the instance URL and API key.") }
            catch(_:Exception) { message("Configuration could not be saved to encrypted device storage.") }
        }
        button("Back") { home() }
    }
    private fun imageSearch() {
        screen("search","Image Search")
        label("Capture the comic cover, move the four corners to its edges, then confirm the perspective-corrected image.")
        button("Capture cover") { if(store.load()==null) { message("Save your instance URL and Metron API key in Configuration first.") } else scan() }
        if(coverFile.exists()) button("Review last capture") { review() }
        button("Back") { home() }
    }
    private fun scan() {
        if(busy)return
        busy=true
        val active=generation
        val scanner=GmsDocumentScanning.getClient(GmsDocumentScannerOptions.Builder()
            .setGalleryImportAllowed(false).setPageLimit(1)
            .setResultFormats(GmsDocumentScannerOptions.RESULT_FORMAT_JPEG)
            .setScannerMode(GmsDocumentScannerOptions.SCANNER_MODE_BASE).build())
        scanner.getStartScanIntent(this).addOnSuccessListener {
            if(active!=generation)return@addOnSuccessListener
            if(isFinishing || isDestroyed) { busy=false;return@addOnSuccessListener }
            capture.launch(IntentSenderRequest.Builder(it).build())
        }.addOnFailureListener {
            if(active!=generation)return@addOnFailureListener
            busy=false;message("Scanner unavailable. Google Play services and its first-use scanner download are required. Try again after the download completes.")
        }
    }
    private fun readCover():Bitmap {
        val bounds=BitmapFactory.Options().apply { inJustDecodeBounds=true };BitmapFactory.decodeFile(coverFile.path,bounds)
        require(bounds.outWidth>0 && bounds.outHeight>0) { "Unreadable cover image." }
        require(bounds.outWidth.toLong()*bounds.outHeight<=32_000_000) { "Cover image is too large. Recapture it." }
        return BitmapFactory.decodeFile(coverFile.path,BitmapFactory.Options().apply { inPreferredConfig=Bitmap.Config.ARGB_8888 }) ?: error("Unreadable cover image.")
    }
    private fun preview(bitmap:Bitmap) {
        column.addView(ImageView(this).apply { setImageBitmap(bitmap);adjustViewBounds=true;contentDescription="Perspective-corrected cover" },LinearLayout.LayoutParams(-1,dp(360)))
    }
    private fun review() {
        screen("review","Confirm cover")
        try { preview(readCover()) } catch(_:Exception) { imageSearch();message("Unable to read this capture. Capture a new cover.");return }
        label("Confirm this corrected image to calculate its hash and search Metron.")
        button("Confirm and search") { search() };button("Retake / adjust corners") { scan() };button("Back") { imageSearch() }
    }
    private fun search() {
        val connection=store.load() ?: run { configuration();return }
        screen("results","Cover matches");val active=generation
        val status=label("Calculating cover hash…")
        button("Capture another") { imageSearch() }
        job=lifecycleScope.launch {
            try {
                val start=SystemClock.elapsedRealtimeNanos()
                val pair=withContext(Dispatchers.Default) {
                    val bitmap=readCover()
                    try {
                        val pixels=IntArray(bitmap.width*bitmap.height);bitmap.getPixels(pixels,0,bitmap.width,0,0,bitmap.width,bitmap.height)
                        PerceptualHash.fromArgb(pixels,bitmap.width,bitmap.height) to ((SystemClock.elapsedRealtimeNanos()-start)/1_000_000.0)
                    } finally { bitmap.recycle() }
                }
                status.text="Hash: ${pair.first}\nSearching Metron…"
                val sent=SystemClock.elapsedRealtimeNanos()
                val response=withContext(Dispatchers.IO) { api.search(connection,pair.first) }
                val roundTrip=(SystemClock.elapsedRealtimeNanos()-sent)/1_000_000.0
                if(active!=generation)return@launch
                val diag=response.optJSONObject("diagnostics")
                status.text="Hash: ${pair.first}\nHash computation: ${ms(pair.second)} ms\nAPI round trip: ${ms(roundTrip)} ms\nDatabase match: ${if(diag?.has("database_match_ms")==true) ms(diag.getDouble("database_match_ms"))+" ms" else "diagnostics disabled"}"
                val results=response.getJSONArray("results")
                if(results.length()==0) label("No searchable covers in this instance.")
                for(i in 0 until results.length()) showResult(results.getJSONObject(i),i+1,connection,active)
            } catch(e:CancellationException) { throw e }
            catch(e:SearchFailure) { if(active==generation) { status.text=e.message;button("Retry search") { search() } } }
            catch(_:Exception) { if(active==generation) { status.text="Search failed. Check the configured address, network, API key, and experimental endpoint.";button("Retry search") { search() } } }
        }
    }
    private fun showResult(row:JSONObject,rank:Int,connection:Connection,active:Int) {
        val match=row.getJSONObject("matched_cover")
        label("$rank. ${row.getString("issue")}",20f)
        label("Distance: ${row.getInt("distance")} / 64 bits\nCover: ${if(match.isNull("variant_id")) "standard" else "variant #"+match.getLong("variant_id")}\nMatched hash: ${match.getString("cover_hash")}",14f)
        val view=ImageView(this).apply { adjustViewBounds=true;contentDescription=row.getString("issue") };column.addView(view,LinearLayout.LayoutParams(-1,dp(300)))
        val url=match.optString("image");if(url.isBlank() || url=="null")return
        lifecycleScope.launch {
            val bitmap=withContext(Dispatchers.IO) { runCatching { api.image(connection,url)?.let { BitmapFactory.decodeByteArray(it,0,it.size) } }.getOrNull() }
            if(active==generation) view.setImageBitmap(bitmap) else bitmap?.recycle()
        }
    }
    private fun ms(value:Double)=String.format(Locale.US,"%.3f",value)
}
