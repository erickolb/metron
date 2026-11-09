package cloud.metron.cphtest

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

data class Connection(val url: String, val token: String)
object InstanceUrl {
    fun normalize(value: String): String {
        val text=value.trim()
        val withScheme=if("://" in text) text else if(text.startsWith("localhost") || text.firstOrNull()?.isDigit()==true) "http://$text" else "https://$text"
        val url=withScheme.toHttpUrlOrNull() ?: throw IllegalArgumentException("Enter a valid http:// or https:// instance URL.")
        require(url.username.isEmpty() && url.password.isEmpty() && url.query==null && url.fragment==null) { "Use an instance URL without credentials, query, or fragment." }
        return url.toString().trimEnd('/')
    }
}
class SearchFailure(message:String): IOException(message)
class MetronApi {
    private val client=OkHttpClient.Builder().connectTimeout(15,TimeUnit.SECONDS)
        .readTimeout(30,TimeUnit.SECONDS).callTimeout(45,TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build()
    fun search(connection: Connection, hash: String): JSONObject {
        require(hash.matches(Regex("[0-9a-f]{16}")))
        val url=(connection.url+"/api/issue/cover-search/").toHttpUrlOrNull()!!.newBuilder().addQueryParameter("cover_hash",hash).build()
        val request=Request.Builder().url(url).header("Authorization","Bearer ${connection.token}")
            .header("Accept","application/json").header("User-Agent","CPHTest/0.2.0").build()
        client.newCall(request).execute().use { response ->
            if(!response.isSuccessful) throw SearchFailure(when(response.code) {
                401,403 -> "API key was rejected (${response.code}). Check Configuration."
                404 -> "Cover-search endpoint not found. Check the instance URL and experimental server branch."
                429 -> "Metron rate limit reached. Retry after ${response.header("Retry-After") ?: "the reset"}."
                else -> "Metron returned HTTP ${response.code}."
            })
            val result=JSONObject(response.body?.string() ?: throw IOException("Empty response."))
            require(result.has("results") && result.getJSONArray("results").length()<=8) { "Unexpected cover-search response." }
            return result
        }
    }
    /** Read-only authentication check; uses the normal issue-list endpoint. */
    fun testConnection(connection:Connection) {
        val url=connection.url+"/api/issue/?series_id=0"
        val request=Request.Builder().url(url).header("Authorization","Bearer ${connection.token}")
            .header("Accept","application/json").build()
        client.newCall(request).execute().use { response ->
            if(!response.isSuccessful)throw SearchFailure("Connection test failed: HTTP ${response.code}.")
            val data=JSONObject(response.body?.string() ?: throw SearchFailure("Empty API response."))
            if(!data.has("results") || !data.has("count"))throw SearchFailure("This URL did not return a Metron issue list.")
        }
    }
    /** TEMPORARY: no artwork or credentials are included in the feedback blob. */
    fun sendFeedback(connection:Connection,note:JSONObject):JSONObject {
        val request=Request.Builder().url(connection.url+"/api/experimental/notetaker/")
            .header("Authorization","Bearer ${connection.token}")
            .post(note.toString().toRequestBody("application/json; charset=utf-8".toMediaType())).build()
        client.newCall(request).execute().use { response ->
            if(!response.isSuccessful)throw SearchFailure("Feedback not saved: HTTP ${response.code}. Retry when the server is available.")
            val receipt=JSONObject(response.body?.string() ?: throw SearchFailure("Empty feedback receipt."))
            if(!receipt.has("id"))throw SearchFailure("Feedback receipt was not recognized.")
            return receipt
        }
    }
    fun image(connection: Connection,url: String): ByteArray? {
        val source=url.toHttpUrlOrNull() ?: return null
        val base=connection.url.toHttpUrlOrNull() ?: return null
        val sameOrigin=source.host==base.host && source.port==base.port && source.scheme==base.scheme
        if(!sameOrigin && !(source.isHttps && source.host in setOf("metron.cloud","static.metron.cloud"))) return null
        // Artwork requests deliberately carry no API credential.
        return client.newCall(Request.Builder().url(source).build()).execute().use {
            if(it.isSuccessful && (it.body?.contentLength() ?: 0)<12_000_000) it.body?.bytes() else null
        }
    }
}
