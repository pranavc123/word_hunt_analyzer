import Foundation

/// A grayscale image (row-major UInt8).
public struct GrayImage: Sendable {
    public let width: Int
    public let height: Int
    public var pixels: [UInt8]

    public init(width: Int, height: Int, pixels: [UInt8]) {
        self.width = width
        self.height = height
        self.pixels = pixels
    }

    @inline(__always) public subscript(x: Int, y: Int) -> UInt8 { pixels[y * width + x] }
}

/// OpenCV COLOR_RGB2GRAY in fixed point: (4899 R + 9617 G + 1868 B + 8192) >> 14.
@inline(__always) public func cvGray(_ r: Int, _ g: Int, _ b: Int) -> UInt8 {
    UInt8((4899 * r + 9617 * g + 1868 * b + 8192) >> 14)
}

/// Port of whcore.letters digit reading: ink blobs right of the colon, each normalised to 20×28 and
/// matched by NCC against templates (fixtures/templates/digits.json).
public struct DigitReader: Sendable {
    public let width: Int
    public let height: Int
    public let inkThreshold: UInt8
    public let templates: [(String, [Double])]

    public init(json url: URL) throws {
        struct File: Decodable {
            let width: Int
            let height: Int
            let ink_threshold: Int
            let templates: [String: [[Double]]]
        }
        let f = try JSONDecoder().decode(File.self, from: Data(contentsOf: url))
        width = f.width
        height = f.height
        inkThreshold = UInt8(f.ink_threshold)
        templates = f.templates.keys.sorted().map { ($0, f.templates[$0]!.flatMap { $0 }) }
    }

    public struct Box: Equatable, Comparable, Sendable {
        public let x, y, w, h, area: Int
        public static func < (a: Box, b: Box) -> Bool { (a.x, a.y, a.w, a.h) < (b.x, b.y, b.w, b.h) }
    }

    /// 8-connected components of `gray < inkThreshold`, area ≥ minArea, sorted like Python.
    public func components(_ img: GrayImage, minArea: Int = 8) -> [Box] {
        var label = [Int32](repeating: 0, count: img.width * img.height)
        var boxes: [Box] = []
        var next: Int32 = 1
        var stack: [Int] = []
        for start in 0..<label.count where label[start] == 0 && img.pixels[start] < inkThreshold {
            var x0 = Int.max, y0 = Int.max, x1 = -1, y1 = -1, area = 0
            label[start] = next
            stack.append(start)
            while let p = stack.popLast() {
                let x = p % img.width, y = p / img.width
                area += 1
                x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
                for dy in -1...1 {
                    for dx in -1...1 where dx != 0 || dy != 0 {
                        let nx = x + dx, ny = y + dy
                        guard nx >= 0, ny >= 0, nx < img.width, ny < img.height else { continue }
                        let q = ny * img.width + nx
                        if label[q] == 0 && img.pixels[q] < inkThreshold {
                            label[q] = next
                            stack.append(q)
                        }
                    }
                }
            }
            next += 1
            if area >= minArea { boxes.append(Box(x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1, area: area)) }
        }
        return boxes.sorted()
    }

    /// Glyph → width×height ink coverage (cv2 INTER_AREA downscale of a 0/1 mask, padded to aspect).
    public func normalise(_ img: GrayImage, _ b: Box) -> [Double] {
        var w = b.w, padLeft = 0
        let target = Double(width) / Double(height)
        if Double(b.w) / Double(b.h) < target {
            let pad = Int((Double(b.h) * target - Double(b.w)).rounded(.toNearestOrEven))
            padLeft = pad / 2
            w = b.w + pad
        }
        let h = b.h
        func ink(_ x: Int, _ y: Int) -> Double {
            let sx = x - padLeft
            guard sx >= 0, sx < b.w else { return 0 }
            return img[b.x + sx, b.y + y] < inkThreshold ? 1 : 0
        }
        var out = [Double](repeating: 0, count: width * height)
        let fx = Double(w) / Double(width), fy = Double(h) / Double(height)
        for oy in 0..<height {
            let sy0 = Double(oy) * fy, sy1 = sy0 + fy
            for ox in 0..<width {
                let sx0 = Double(ox) * fx, sx1 = sx0 + fx
                var acc = 0.0
                var y = Int(sy0)
                while Double(y) < sy1 && y < h {
                    let wy = min(sy1, Double(y + 1)) - max(sy0, Double(y))
                    var x = Int(sx0)
                    while Double(x) < sx1 && x < w {
                        let wx = min(sx1, Double(x + 1)) - max(sx0, Double(x))
                        acc += ink(x, y) * wx * wy
                        x += 1
                    }
                    y += 1
                }
                out[oy * width + ox] = acc / (fx * fy)
            }
        }
        return out
    }

    public static func ncc(_ a: [Double], _ b: [Double]) -> Double {
        let ma = a.reduce(0, +) / Double(a.count), mb = b.reduce(0, +) / Double(b.count)
        var sab = 0.0, saa = 0.0, sbb = 0.0
        for i in 0..<a.count {
            let x = a[i] - ma, y = b[i] - mb
            sab += x * y; saa += x * x; sbb += y * y
        }
        let d = (saa * sbb).squareRoot()
        return d > 0 ? sab / d : 0
    }

    public func classify(_ glyph: [Double]) -> (String, Double) {
        var best = ("", -2.0)
        for (ch, t) in templates {
            let s = Self.ncc(glyph, t)
            if s > best.1 { best = (ch, s) }
        }
        return best
    }

    /// Digits of a "LABEL: 123" line: tall blobs right of the colon. (value, min match score).
    public func readNumber(_ img: GrayImage) -> (Int?, Double) {
        let boxes = components(img)
        guard let tall = boxes.map(\.h).max() else { return (nil, 0) }
        let small = boxes.filter { Double($0.h) < 0.6 * Double(tall) && Double($0.w) < 0.6 * Double(tall) }
        guard let colon = small.map({ $0.x + $0.w }).max() else { return (nil, 0) }
        let digits = boxes.filter { $0.x > colon && Double($0.h) >= 0.75 * Double(tall) }
        guard !digits.isEmpty else { return (nil, 0) }
        var s = "", worst = 1.0
        for b in digits {
            let (ch, score) = classify(normalise(img, b))
            s += ch
            worst = min(worst, score)
        }
        return (Int(s), worst)
    }
}
