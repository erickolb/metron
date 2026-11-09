package cloud.metron.cphtest

import org.json.JSONObject
import java.util.UUID

/** TEMPORARY research feedback. Remove with the experimental notetaker before upstream. */
object FeedbackNote {
    fun rank(response:JSONObject,index:Int):Int {
        val results=response.getJSONArray("results")
        val distance=results.getJSONObject(index).getInt("distance")
        return 1+(0 until results.length()).count { results.getJSONObject(it).getInt("distance")<distance }
    }
    fun create(response:JSONObject,index:Int?,hashMs:Double,roundTripMs:Double):JSONObject {
        val selected=index?.let { response.getJSONArray("results").getJSONObject(it) }
        return JSONObject().put("schema_version",1).put("event_id",UUID.randomUUID().toString())
            .put("client","CPHTest/0.2.0").put("outcome",if(index==null) "no_match" else "match")
            .put("search_hash",response.getString("cover_hash"))
            .put("selected_comic",selected?.let { JSONObject(it.toString()) } ?: JSONObject.NULL)
            .put("array_position",index?.plus(1) ?: JSONObject.NULL)
            .put("rank",index?.let { rank(response,it) } ?: JSONObject.NULL)
            .put("bits_off",selected?.getInt("distance") ?: JSONObject.NULL)
            .put("performance",response.optJSONObject("diagnostics")?.let { JSONObject(it.toString()) } ?: JSONObject.NULL)
            .put("client_timing",JSONObject().put("hash_ms",hashMs).put("api_round_trip_ms",roundTripMs))
            .put("results",org.json.JSONArray(response.getJSONArray("results").toString()))
    }
}
