package cloud.metron.cphtest

import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class MetronApiTest {
    @Test fun authenticatesOnlySearchAndSendsOnlyHash() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("{\"results\":[],\"diagnostics\":{\"database_match_ms\":1.5}}"))
            server.enqueue(MockResponse().setBody("image"))
            val connection=Connection(server.url("/").toString().trimEnd('/'),"unit-test-key")
            val api=MetronApi();val result=api.search(connection,"8000000000000000")
            assertEquals(1.5,result.getJSONObject("diagnostics").getDouble("database_match_ms"),0.0)
            val request=server.takeRequest()
            assertEquals("/api/issue/cover-search/?cover_hash=8000000000000000",request.path)
            assertEquals("Bearer unit-test-key",request.getHeader("Authorization"));assertEquals(0,request.bodySize)
            api.image(connection,server.url("/cover.jpg").toString())
            assertNull(server.takeRequest().getHeader("Authorization"))
        }
    }
    @Test fun rejectsRedirectInsteadOfForwardingCredential() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(302).setHeader("Location","https://example.com/"))
            try { MetronApi().search(Connection(server.url("/").toString().trimEnd('/'),"unit-test-key"),"8000000000000000");fail() }
            catch(_:java.io.IOException) { assertEquals(1,server.requestCount) }
        }
    }
    @Test fun normalizesInstanceAddresses() {
        assertEquals("http://192.168.1.12:8000",InstanceUrl.normalize("192.168.1.12:8000"))
        assertEquals("https://metron.cloud",InstanceUrl.normalize("metron.cloud/"))
        for(url in listOf("https://user:secret@example.com/","https://example.com/?token=bad","file:///bad")) {
            try { InstanceUrl.normalize(url);fail(url) } catch(_:IllegalArgumentException) { }
        }
    }
    @Test fun connectionProbeIsReadOnlyAndUsesEnteredCredentials() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("{\"count\":0,\"results\":[]}"))
            MetronApi().testConnection(Connection(server.url("/").toString().trimEnd('/'),"draft-key"))
            val request=server.takeRequest()
            assertEquals("GET",request.method);assertEquals("/api/issue/?series_id=0",request.path)
            assertEquals("Bearer draft-key",request.getHeader("Authorization"))
        }
    }
    @Test fun postsFeedbackAndRequiresSuccessfulReceipt() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(201).setBody("{\"id\":\"test-receipt\"}"))
            server.enqueue(MockResponse().setResponseCode(503))
            val connection=Connection(server.url("/").toString().trimEnd('/'),"unit-test-key")
            val note=org.json.JSONObject("{\"outcome\":\"no_match\"}")
            val api=MetronApi()
            assertEquals("test-receipt",api.sendFeedback(connection,note).getString("id"))
            val request=server.takeRequest()
            assertEquals("POST",request.method);assertEquals("/api/experimental/notetaker/",request.path)
            assertEquals(note.toString(),request.body.readUtf8())
            assertEquals("Bearer unit-test-key",request.getHeader("Authorization"))
            try { api.sendFeedback(connection,note);fail() } catch(_:SearchFailure) { }
        }
    }
}
