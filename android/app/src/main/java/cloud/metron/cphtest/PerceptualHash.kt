package cloud.metron.cphtest

import kotlin.math.*

/** ImageHash phash(hash_size=8, highfreq_factor=4): Pillow L/Lanczos, DCT-II, median. */
object PerceptualHash {
    private const val N = 32
    private const val PRECISION = 1 shl 22
    private val cosines = Array(8) { k -> DoubleArray(N) { x -> cos(PI * (2*x+1) * k / (2*N)) } }
    private fun sinc(x: Double) = if (x == 0.0) 1.0 else sin(PI*x)/(PI*x)
    private fun lanczos(x: Double) = if (abs(x) < 3.0) sinc(x)*sinc(x/3) else 0.0
    private data class Kernel(val start: Int, val weights: IntArray)
    private fun kernels(size: Int): Array<Kernel> {
        val scale = size.toDouble()/N
        val filterScale = max(1.0, scale)
        val support = 3.0*filterScale
        return Array(N) { target ->
            val center = (target+0.5)*scale
            val start = max(0, (center-support+0.5).toInt())
            val end = min(size, (center+support+0.5).toInt())
            val weights = DoubleArray(end-start) { x -> lanczos((x+start-center+0.5)/filterScale) }
            val sum = weights.sum()
            Kernel(start, IntArray(weights.size) { x ->
                val weight = weights[x]/sum*PRECISION
                (weight + if (weight < 0) -0.5 else 0.5).toInt()
            })
        }
    }
    /** RGB conversion uses Pillow's fixed-point luminance coefficients. */
    fun fromArgb(pixels: IntArray, width: Int, height: Int): String {
        val gray = IntArray(pixels.size) { i ->
            val p=pixels[i]
            (((p ushr 16 and 255)*19595 + (p ushr 8 and 255)*38470 +
                (p and 255)*7471 + 32768) ushr 16)
        }
        return fromGray(gray, width, height)
    }
    fun fromGray(gray: IntArray, width: Int, height: Int): String {
        require(width > 0 && height > 0 && gray.size == width*height)
        fun resizeX(input: IntArray, w: Int, h: Int): IntArray {
            if(w==N)return input
            val output=IntArray(N*h);val xk=kernels(w)
            for(y in 0 until h) for(x in 0 until N) {
                val kernel=xk[x];var sum=1L shl 21
                for(j in kernel.weights.indices) sum+=input[y*w+kernel.start+j].toLong()*kernel.weights[j]
                output[y*N+x]=(sum shr 22).toInt().coerceIn(0,255)
            }
            return output
        }
        fun resizeY(input: IntArray, w: Int, h: Int): IntArray {
            if(h==N)return input
            val output=IntArray(w*N);val yk=kernels(h)
            for(y in 0 until N) for(x in 0 until w) {
                val kernel=yk[y];var sum=1L shl 21
                for(j in kernel.weights.indices) sum+=input[(kernel.start+j)*w+x].toLong()*kernel.weights[j]
                output[y*w+x]=(sum shr 22).toInt().coerceIn(0,255)
            }
            return output
        }
        // Pillow chooses the vertical pass first for strongly asymmetric reductions.
        val resized=if(height-N>0 && height-N>(width-N)*2)
            resizeX(resizeY(gray,width,height),width,N)
        else resizeY(resizeX(gray,width,height),N,height)
        val vertical = Array(8) { DoubleArray(N) }
        for (k in 0 until 8) for (x in 0 until N)
            for (y in 0 until N) vertical[k][x] += resized[y*N+x]*cosines[k][y]*2
        val dct = DoubleArray(64)
        for (y in 0 until 8) for (x in 0 until 8) {
            var sum=0.0
            for (j in 0 until N) sum += vertical[y][j]*cosines[x][j]*2
            dct[y*8+x]=if(abs(sum)<1e-7) 0.0 else sum
        }
        val sorted=dct.sorted();val median=(sorted[31]+sorted[32])/2
        var hash=0L
        for (value in dct) hash=(hash shl 1) or if(value>median) 1L else 0L
        return java.lang.Long.toUnsignedString(hash,16).padStart(16,'0')
    }
}
