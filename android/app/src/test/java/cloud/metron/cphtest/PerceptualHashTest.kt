package cloud.metron.cphtest

import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test

class PerceptualHashTest {
    @Test fun matchesPythonImageHashAcrossImageSizes() {
        val vectors=JSONArray(javaClass.getResource("/phash-vectors.json")!!.readText())
        for(i in 0 until vectors.length()) {
            val v=vectors.getJSONObject(i)
            var state=v.getLong("seed")
            val argb=IntArray(v.getInt("width")*v.getInt("height")) {
                var pixel=255 shl 24
                for(shift in intArrayOf(16,8,0)) {
                    state=(1664525L*state+1013904223L) and 0xffffffffL
                    pixel=pixel or ((state ushr 24).toInt() shl shift)
                }
                if(v.getBoolean("white")) -1 else pixel
            }
            assertEquals("vector $i",v.getString("hash"),PerceptualHash.fromArgb(argb,v.getInt("width"),v.getInt("height")))
        }
    }
}
