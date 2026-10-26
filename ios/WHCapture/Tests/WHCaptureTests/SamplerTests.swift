import CoreGraphics
import CoreVideo
import Foundation
import ImageIO
import XCTest
@testable import WHCapture

/// S2.T3: the Swift sampler on pixel buffers built from fixtures/crops matches the Python sampler
/// (fixtures/expected/sampler.json) and reads the banner digits exactly.
final class SamplerTests: XCTestCase {
    static let root = SchemaTests.root
    static let calibration = try! Calibration.load(root.appendingPathComponent("fixtures/calibration/iphone-1206x2622.json"))
    static let digits = try! DigitReader(json: root.appendingPathComponent("fixtures/templates/digits.json"))

    // MARK: image helpers

    struct RGBImage {
        let width: Int, height: Int
        var px: [UInt8]  // RGB
    }

    static func loadRGB(_ rel: String) throws -> RGBImage {
        let url = root.appendingPathComponent("fixtures/\(rel)")
        let src = try XCTUnwrap(CGImageSourceCreateWithURL(url as CFURL, nil))
        let img = try XCTUnwrap(CGImageSourceCreateImageAtIndex(src, 0, nil))
        let w = img.width, h = img.height
        var rgba = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = CGContext(data: &rgba, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                            space: CGColorSpace(name: CGColorSpace.sRGB)!,
                            bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
        var rgb = [UInt8](repeating: 0, count: w * h * 3)
        for i in 0..<(w * h) { rgb[3 * i] = rgba[4 * i]; rgb[3 * i + 1] = rgba[4 * i + 1]; rgb[3 * i + 2] = rgba[4 * i + 2] }
        return RGBImage(width: w, height: h, px: rgb)
    }

    static func loadGray(_ rel: String) throws -> GrayImage {
        let url = root.appendingPathComponent("fixtures/\(rel)")
        let src = try XCTUnwrap(CGImageSourceCreateWithURL(url as CFURL, nil))
        let img = try XCTUnwrap(CGImageSourceCreateImageAtIndex(src, 0, nil))
        let w = img.width, h = img.height
        var px = [UInt8](repeating: 0, count: w * h)
        let ctx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                            space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)!
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
        return GrayImage(width: w, height: h, pixels: px)
    }

    /// A full calibration-size frame filled with `fill`, with `patches` pasted at their origins.
    static func frame(fill: [UInt8], patches: [(RGBImage, Int, Int)], width: Int = 1206, height: Int = 2622) -> RGBImage {
        var px = [UInt8](repeating: 0, count: width * height * 3)
        for i in 0..<(width * height) { px[3 * i] = fill[0]; px[3 * i + 1] = fill[1]; px[3 * i + 2] = fill[2] }
        for (p, x0, y0) in patches {
            for y in 0..<p.height {
                for x in 0..<p.width {
                    let d = 3 * ((y0 + y) * width + x0 + x), s = 3 * (y * p.width + x)
                    px[d] = p.px[s]; px[d + 1] = p.px[s + 1]; px[d + 2] = p.px[s + 2]
                }
            }
        }
        return RGBImage(width: width, height: height, px: px)
    }

    static func bgraBuffer(_ img: RGBImage) -> CVPixelBuffer {
        var pb: CVPixelBuffer?
        CVPixelBufferCreate(nil, img.width, img.height, kCVPixelFormatType_32BGRA, nil, &pb)
        let buf = pb!
        CVPixelBufferLockBaseAddress(buf, [])
        let base = CVPixelBufferGetBaseAddress(buf)!.assumingMemoryBound(to: UInt8.self)
        let stride = CVPixelBufferGetBytesPerRow(buf)
        for y in 0..<img.height {
            for x in 0..<img.width {
                let s = 3 * (y * img.width + x), d = y * stride + 4 * x
                base[d] = img.px[s + 2]; base[d + 1] = img.px[s + 1]; base[d + 2] = img.px[s]; base[d + 3] = 255
            }
        }
        CVPixelBufferUnlockBaseAddress(buf, [])
        return buf
    }

    /// Full-range BT.709 4:2:0 (what ReplayKit delivers as 420f), chroma averaged over 2×2.
    static func yuv420fBuffer(_ img: RGBImage) -> CVPixelBuffer {
        var pb: CVPixelBuffer?
        CVPixelBufferCreate(nil, img.width, img.height, kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, nil, &pb)
        let buf = pb!
        CVBufferSetAttachment(buf, kCVImageBufferYCbCrMatrixKey, kCVImageBufferYCbCrMatrix_ITU_R_709_2, .shouldPropagate)
        CVPixelBufferLockBaseAddress(buf, [])
        let yb = CVPixelBufferGetBaseAddressOfPlane(buf, 0)!.assumingMemoryBound(to: UInt8.self)
        let cb = CVPixelBufferGetBaseAddressOfPlane(buf, 1)!.assumingMemoryBound(to: UInt8.self)
        let ys = CVPixelBufferGetBytesPerRowOfPlane(buf, 0), cs = CVPixelBufferGetBytesPerRowOfPlane(buf, 1)
        func clamp(_ v: Double) -> UInt8 { UInt8(min(255, max(0, v.rounded()))) }
        for y in stride(from: 0, to: img.height, by: 2) {
            for x in stride(from: 0, to: img.width, by: 2) {
                var su = 0.0, sv = 0.0, n = 0.0
                for dy in 0..<2 where y + dy < img.height {
                    for dx in 0..<2 where x + dx < img.width {
                        let s = 3 * ((y + dy) * img.width + x + dx)
                        let r = Double(img.px[s]), g = Double(img.px[s + 1]), b = Double(img.px[s + 2])
                        let Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
                        yb[(y + dy) * ys + x + dx] = clamp(Y)
                        su += (b - Y) / 1.8556; sv += (r - Y) / 1.5748; n += 1
                    }
                }
                cb[(y / 2) * cs + x] = clamp(su / n + 128)
                cb[(y / 2) * cs + x + 1] = clamp(sv / n + 128)
            }
        }
        CVPixelBufferUnlockBaseAddress(buf, [])
        return buf
    }

    static func expectedFrames() throws -> [[String: Any]] {
        let url = root.appendingPathComponent("fixtures/expected/sampler.json")
        let obj = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        return obj["frames"] as! [[String: Any]]
    }

    func compare(_ row: SampleRow, _ expected: [String: Double], keys: [String], tol: Double, _ label: String) {
        for k in keys {
            let got = row[k] ?? .nan, want = expected[k] ?? .nan
            XCTAssertLessThanOrEqual(abs(got - want), tol, "\(label) \(k): \(got) vs \(want)")
        }
    }

    static let tileKeys = (0..<16).flatMap { i in ["r", "g", "b"].map { "t\(i)_\($0)" } }
    static let roiKeys = Calibration.roiKeys.flatMap { k in ["r", "g", "b", "std"].map { "\(k)_\($0)" } }

    // MARK: tests

    func testBGRAMatchesPythonSampler() throws {
        for f in try Self.expectedFrames() {
            let crop = try Self.loadRGB(f["crop"] as! String)
            let origin = f["origin"] as! [Int]
            let img = Self.frame(fill: [40, 60, 40], patches: [(crop, origin[0], origin[1])])
            let s = Sampler(calibration: Self.calibration, digits: Self.digits, roiStride: 1)
            let row = try XCTUnwrap(s.sample(Self.bgraBuffer(img), frame: 0, tMs: 0))
            let want = f["values"] as! [String: Double]
            compare(row, want, keys: Self.tileKeys, tol: 2, "BGRA \(f["crop"]!)")
            compare(row, want, keys: Self.roiKeys, tol: 2, "BGRA \(f["crop"]!)")
        }
    }

    func testYUV420fCloseToPythonSampler() throws {
        for f in try Self.expectedFrames() {
            let crop = try Self.loadRGB(f["crop"] as! String)
            let origin = f["origin"] as! [Int]
            let img = Self.frame(fill: [40, 60, 40], patches: [(crop, origin[0], origin[1])])
            let s = Sampler(calibration: Self.calibration, digits: Self.digits, roiStride: 2)
            let row = try XCTUnwrap(s.sample(Self.yuv420fBuffer(img), frame: 0, tMs: 0))
            compare(row, f["values"] as! [String: Double], keys: Self.tileKeys, tol: 3, "420f \(f["crop"]!)")
        }
    }

    func testReadsBannerDigits() throws {
        let cases: [(String, Int)] = [("end_words_65", 65), ("end_score_44700", 44700), ("end_score_28000", 28000),
                                      ("banner_words_64", 64), ("banner_score_38300", 38300)]
        for (name, value) in cases {
            let (got, conf) = Self.digits.readNumber(try Self.loadGray("crops/\(name).png"))
            XCTAssertEqual(got, value, name)
            XCTAssertGreaterThan(conf, 0.5, name)
        }
    }

    func testWordsReadOnlyOnBoardFrames() throws {
        let words = try Self.loadRGB("crops/banner_words_64.png")
        let r = Self.calibration.roi_banner_words
        let img = Self.frame(fill: [255, 255, 255], patches: [(words, r[0], r[1])])
        let s = Sampler(calibration: Self.calibration, digits: Self.digits)
        s.classify = { _ in .board }
        XCTAssertEqual(s.sample(Self.bgraBuffer(img), frame: 0, tMs: 0)?["words"], 64)
        s.classify = { _ in .other }
        XCTAssertTrue(s.sample(Self.bgraBuffer(img), frame: 1, tMs: 33)!["words"]!.isNaN)
    }

    func testListShiftOnScrollingFrames() throws {
        // a tall random "list" scrolled up by 100 then 150 px
        var rng = SystemRandomNumberGenerator()
        let tall = RGBImage(width: 1206, height: 5000, px: (0..<(1206 * 5000 * 3)).map { _ in UInt8.random(in: 0...255, using: &rng) })
        func view(_ top: Int) -> RGBImage {
            RGBImage(width: 1206, height: 2622, px: Array(tall.px[(3 * 1206 * top)..<(3 * 1206 * (top + 2622))]))
        }
        let s = Sampler(calibration: Self.calibration, digits: Self.digits)
        s.classify = { _ in .allWords }
        let shifts = [1000, 1100, 1250].map { s.sample(Self.bgraBuffer(view($0)), frame: 0, tMs: 0)!["list_shift"]! }
        XCTAssertTrue(shifts[0].isNaN)
        XCTAssertEqual(Array(shifts[1...]), [100, 150])
    }

    func testScaledCalibrationRects() {
        let c = Self.calibration
        let r = c.scaled(c.sample_rects[0], toWidth: 884, height: 1920)
        XCTAssertEqual(r[2], max(1, Int((Double(c.sample_rects[0][2]) * 884 / 1206).rounded(.toNearestOrEven))))
        XCTAssertEqual(c.scaled(c.roi_banner, toWidth: 1206, height: 2622), c.roi_banner)
    }
}

final class SamplerSpeedTests: XCTestCase {
    /// Timing on a phone-sized 884×1920 420f buffer (prints ms/frame; asserts only a loose bound).
    func testSamplerSpeedOnPhoneSizedFrames() throws {
        let fill = SamplerTests.frame(fill: [100, 140, 100], patches: [], width: 884, height: 1920)
        let pb = SamplerTests.yuv420fBuffer(fill)
        let s = Sampler(calibration: SamplerTests.calibration, digits: SamplerTests.digits)
        for screen in [Screen.board, .allWords, .other] {
            s.classify = { _ in screen }
            let t0 = Date()
            for i in 0..<30 { _ = s.sample(pb, frame: i, tMs: i * 33) }
            let ms = Date().timeIntervalSince(t0) / 30 * 1000
            print("sampler \(screen): \(String(format: "%.2f", ms)) ms/frame")
            XCTAssertLessThan(ms, 500)
        }
    }
}
