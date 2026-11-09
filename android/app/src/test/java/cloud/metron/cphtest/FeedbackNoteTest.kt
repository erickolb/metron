package cloud.metron.cphtest

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class FeedbackNoteTest {
    private fun response()=JSONObject("""{"cover_hash":"0123456789abcdef","results":[{"id":1,"issue":"First","distance":8},{"id":2,"issue":"Second","distance":8},{"id":3,"issue":"Third","distance":10}],"diagnostics":{"database_match_ms":2.75,"hashes_checked":2299}}""")
    @Test fun preservesTiesAndOriginalArrayPosition() {
        val r=response()
        assertEquals(1,FeedbackNote.rank(r,0));assertEquals(1,FeedbackNote.rank(r,1));assertEquals(3,FeedbackNote.rank(r,2))
        val note=FeedbackNote.create(r,1,12.0,34.0)
        assertEquals("match",note.getString("outcome"));assertEquals(1,note.getInt("rank"));assertEquals(2,note.getInt("array_position"))
        assertEquals(8,note.getInt("bits_off"));assertEquals(2,note.getJSONObject("selected_comic").getInt("id"))
        assertEquals("0123456789abcdef",note.getString("search_hash"))
        assertEquals(r.getJSONObject("diagnostics").toString(),note.getJSONObject("performance").toString())
        assertEquals(3,note.getJSONArray("results").length())
    }
    @Test fun reportsFailureWithoutInventingAMatch() {
        val note=FeedbackNote.create(response(),null,12.0,34.0)
        assertEquals("no_match",note.getString("outcome"))
        for(key in listOf("selected_comic","rank","array_position","bits_off"))assertTrue(note.isNull(key))
        assertEquals(2299,note.getJSONObject("performance").getInt("hashes_checked"))
    }
}
