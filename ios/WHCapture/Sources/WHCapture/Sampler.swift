import CoreVideo
import Foundation

/// Read-only view of a locked CVPixelBuffer (32BGRA, or 420f/420v bi-planar YCbCr).
public struct FrameView {
    public let width: Int
    public let height: Int
    let format: OSType
    let base0: UnsafePointer<UInt8>
    let base1: UnsafePointer<UInt8>?
    let stride0: Int
    let stride1: Int
    let bt709: Bool
    let fullRange: Bool

    /// Call between CVPixelBufferLockBaseAddress/Unlock.
    public init?(_ pb: CVPixelBuffer) {
        width = CVPixelBufferGetWidth(pb)
        height = CVPixelBufferGetHeight(pb)
        format = CVPixelBufferGetPixelFormatType(pb)
        switch format {
        case kCVPixelFormatType_32BGRA:
            guard let b = CVPixelBufferGetBaseAddress(pb) else { return nil }
            base0 = UnsafePointer(b.assumingMemoryBound(to: UInt8.self))
            base1 = nil
            stride0 = CVPixelBufferGetBytesPerRow(pb)
            stride1 = 0
            fullRange = true
        case kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange:
            guard let y = CVPixelBufferGetBaseAddressOfPlane(pb, 0),
                  let c = CVPixelBufferGetBaseAddressOfPlane(pb, 1) else { return nil }
            base0 = UnsafePointer(y.assumingMemoryBound(to: UInt8.self))
            base1 = UnsafePointer(c.assumingMemoryBound(to: UInt8.self))
            stride0 = CVPixelBufferGetBytesPerRowOfPlane(pb, 0)
            stride1 = CVPixelBufferGetBytesPerRowOfPlane(pb, 1)
            fullRange = format == kCVPixelFormatType_420YpCbCr8BiPlanarFullRange
        default:
            return nil
        }
        let matrix = CVBufferCopyAttachment(pb, kCVImageBufferYCbCrMatrixKey, nil) as? String
        bt709 = matrix == (kCVImageBufferYCbCrMatrix_ITU_R_709_2 as String)
    }

    @inline(__always) public func rgb(_ x: Int, _ y: Int) -> (Int, Int, Int) {
        if base1 == nil {
            let p = base0 + y * stride0 + 4 * x
            return (Int(p[2]), Int(p[1]), Int(p[0]))
        }
        var Y = Double(base0[y * stride0 + x])
        let c = base1! + (y / 2) * stride1 + (x / 2) * 2
        var U = Double(c[0]) - 128, V = Double(c[1]) - 128
        if !fullRange { Y = (Y - 16) * 255 / 219; U *= 255 / 224; V *= 255 / 224 }
        let r, g, b: Double
        if bt709 {
            r = Y + 1.5748 * V; g = Y - 0.1873 * U - 0.4681 * V; b = Y + 1.8556 * U
        } else {
            r = Y + 1.402 * V; g = Y - 0.344136 * U - 0.714136 * V; b = Y + 1.772 * U
        }
        @inline(__always) func clamp(_ v: Double) -> Int { Int(min(255, max(0, v.rounded()))) }
        return (clamp(r), clamp(g), clamp(b))
    }

    /// Mean RGB of a rect (every `stride`-th pixel in both directions).
    public func meanRGB(_ r: [Int], stride: Int = 1) -> [Double] {
        var sr = 0, sg = 0, sb = 0, n = 0
        var y = r[1]
        while y < min(height, r[1] + r[3]) {
            var x = r[0]
            while x < min(width, r[0] + r[2]) {
                let (a, b, c) = rgb(x, y)
                sr += a; sg += b; sb += c; n += 1
                x += stride
            }
            y += stride
        }
        let d = Double(max(1, n))
        return [Double(sr) / d, Double(sg) / d, Double(sb) / d]
    }

    /// Mean RGB and the population std of per-pixel (r+g+b)/3 over a rect.
    public func meanAndStd(_ r: [Int], stride: Int = 1) -> ([Double], Double) {
        var sr = 0.0, sg = 0.0, sb = 0.0, s1 = 0.0, s2 = 0.0, n = 0.0
        var y = r[1]
        while y < min(height, r[1] + r[3]) {
            var x = r[0]
            while x < min(width, r[0] + r[2]) {
                let (a, b, c) = rgb(x, y)
                let m = Double(a + b + c) / 3
                sr += Double(a); sg += Double(b); sb += Double(c); s1 += m; s2 += m * m; n += 1
                x += stride
            }
            y += stride
        }
        n = max(1, n)
        let mean = s1 / n
        return ([sr / n, sg / n, sb / n], max(0, s2 / n - mean * mean).squareRoot())
    }

    /// OpenCV-gray crop of a rect.
    public func gray(_ r: [Int]) -> GrayImage {
        let w = max(0, min(width, r[0] + r[2]) - r[0]), h = max(0, min(height, r[1] + r[3]) - r[1])
        var px = [UInt8](repeating: 0, count: w * h)
        for yy in 0..<h {
            for xx in 0..<w {
                let (a, b, c) = rgb(r[0] + xx, r[1] + yy)
                px[yy * w + xx] = cvGray(a, b, c)
            }
        }
        return GrayImage(width: w, height: h, pixels: px)
    }

    /// Per-row mean of (r+g+b)/3 over columns [x0, x1) for rows [y0, y1), every `stride`-th column.
    public func rowProfile(y0: Int, y1: Int, x0: Int, x1: Int, stride: Int = 1) -> [Double] {
        (y0..<min(y1, height)).map { y in
            var s = 0, n = 0
            var x = x0
            while x < min(x1, width) {
                let (a, b, c) = rgb(x, y)
                s += a + b + c; n += 3
                x += stride
            }
            return Double(s) / Double(max(1, n))
        }
    }
}

/// Port of whcore.oracle.sampler `Sampler`: one frame → one sample row (fixtures/samples/README.md).
public final class Sampler {
    public let calibration: Calibration
    public let digits: DigitReader
    /// Large ROIs (banner, end list…) are sampled every `roiStride`-th pixel; tiles are full-res.
    public var roiStride: Int
    /// The 64-bin whole-frame profile is not used by the machine; skip it on the device.
    public var includeProfile: Bool
    public var classify: (SampleRow) -> Screen = Screens.classify

    private var prevProfile: [Double]?
    private var velocity = 0  // in calibration px

    public init(calibration: Calibration, digits: DigitReader, roiStride: Int = 2, includeProfile: Bool = false) {
        self.calibration = calibration
        self.digits = digits
        self.roiStride = roiStride
        self.includeProfile = includeProfile
    }

    public func sample(_ pb: CVPixelBuffer, frame: Int, tMs: Int) -> SampleRow? {
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard let view = FrameView(pb) else { return nil }
        return sample(view, frame: frame, tMs: tMs)
    }

    public func sample(_ v: FrameView, frame: Int, tMs: Int) -> SampleRow {
        let cal = calibration
        func sc(_ r: [Int]) -> [Int] { cal.scaled(r, toWidth: v.width, height: v.height) }
        var row: SampleRow = ["frame": Double(frame), "t_ms": Double(tMs)]
        for (i, r) in cal.sample_rects.enumerated() {
            let m = v.meanRGB(sc(r))
            row["t\(i)_r"] = m[0]; row["t\(i)_g"] = m[1]; row["t\(i)_b"] = m[2]
        }
        for key in Calibration.roiKeys {
            let (m, std) = v.meanAndStd(sc(cal.roi(key)), stride: roiStride)
            row["\(key)_r"] = m[0]; row["\(key)_g"] = m[1]; row["\(key)_b"] = m[2]
            row["\(key)_std"] = std
        }
        if includeProfile {
            let rows = v.rowProfile(y0: 0, y1: v.height, x0: 0, x1: v.width, stride: 4)
            for (k, bin) in Sampler.arraySplit(rows, 64).enumerated() {
                row["p\(k)"] = bin.reduce(0, +) / Double(max(1, bin.count))
            }
        }
        let screen = classify(row)
        row["words"] = .nan
        if screen == .board, let w = digits.readNumber(v.gray(sc(cal.roi_banner_words))).0 {
            row["words"] = Double(w)
        }
        row["list_shift"] = .nan
        if screen == .allWords {
            let band = sc(Calibration.listBandRect)
            let xs = sc([330, 612, 940 - 330, 1])  // profile columns of the list band
            let prof = v.rowProfile(y0: band[1], y1: band[1] + band[3], x0: xs[0], x1: xs[0] + xs[2])
            let scale = Double(v.height) / Double(cal.height)
            if let prev = prevProfile {
                let s = Sampler.estimateShift(prev, prof, predicted: Int((Double(velocity) * scale).rounded()),
                                              maxShift: Int(1500 * scale), minOverlap: Int(300 * scale))
                let calPx = Int((Double(s) / scale).rounded(.toNearestOrEven))
                velocity = calPx
                row["list_shift"] = Double(calPx)
            }
            prevProfile = prof
        } else {
            prevProfile = nil
            velocity = 0
        }
        return row
    }

    /// numpy.array_split: the first (n % k) parts get one extra element.
    static func arraySplit(_ a: [Double], _ k: Int) -> [ArraySlice<Double>] {
        let q = a.count / k, r = a.count % k
        var out: [ArraySlice<Double>] = [], i = 0
        for j in 0..<k {
            let n = q + (j < r ? 1 : 0)
            out.append(a[i..<(i + n)])
            i += n
        }
        return out
    }

    /// Port of whcore.allwords.estimate_shift: s minimising mean |cur[y] − prev[y+s]| + 0.004|s − predicted|.
    public static func estimateShift(_ prev: [Double], _ cur: [Double], predicted: Int = 0,
                                     maxShift: Int = 1500, minOverlap: Int = 300) -> Int {
        let n = min(prev.count, cur.count)
        var bestScore = Double.infinity, best = 0
        prev.withUnsafeBufferPointer { p in
            cur.withUnsafeBufferPointer { c in
                for s in -maxShift...maxShift {
                    let a0 = max(0, -s), a1 = min(n, n - s)
                    if a1 - a0 < minOverlap { continue }
                    var acc = 0.0
                    for y in a0..<a1 { acc += abs(c[y] - p[y + s]) }
                    let score = acc / Double(a1 - a0) + 0.004 * Double(abs(s - predicted))
                    if score < bestScore { bestScore = score; best = s }
                }
            }
        }
        return best
    }
}
