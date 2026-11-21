import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Extracts the bitmap stored in an EMF+ `EmfPlusBitmap` record.
///
/// Word stores screenshots and table fragments as EMF+ bitmaps rather than
/// separate image files.  `libemf2svg` ignores EMF+ records, so this parser
/// reads the raw BGRA/BGR pixels and flattens them onto white for OCR.
public enum EMFPlusExtractor {
    private static let emfComment: UInt32 = 70
    private static let emfPlusID: UInt32 = 0x2B464D45  // "EMF+"
    private static let emfPlusBitmap: UInt16 = 0x4008

    public static func extract(emf: URL, outPNG: URL) -> Bool {
        guard let data = try? Data(contentsOf: emf) else { return false }
        let chunks = plusChunks(in: data)
        for (start, end) in chunks {
            var cursor = start
            while cursor + 12 <= end {
                guard let recordType = readUInt16(data, cursor),
                      let recordSize = readUInt32(data, cursor + 4),
                      recordSize >= 12,
                      cursor + Int(recordSize) <= end else {
                    break
                }
                if recordType == emfPlusBitmap, recordSize > 40 {
                    if extractBitmap(data, cursor: cursor, outPNG: outPNG) {
                        return true
                    }
                }
                cursor += Int(recordSize)
            }
        }
        return false
    }

    private static func plusChunks(in data: Data) -> [(Int, Int)] {
        var chunks: [(Int, Int)] = []
        var offset = 0
        while offset + 8 <= data.count {
            guard let recordType = readUInt32(data, offset),
                  let recordSize = readUInt32(data, offset + 4),
                  recordSize >= 8,
                  offset + Int(recordSize) <= data.count else {
                break
            }
            if recordType == emfComment, offset + 16 <= data.count,
               let commentID = readUInt32(data, offset + 8),
               commentID == emfPlusID {
                chunks.append((offset + 16, offset + Int(recordSize)))
            }
            offset += Int(recordSize)
        }
        return chunks
    }

    private static func extractBitmap(_ data: Data, cursor: Int, outPNG: URL) -> Bool {
        guard let width32 = readUInt32(data, cursor + 20),
              let height32 = readUInt32(data, cursor + 24),
              let stride32 = readUInt32(data, cursor + 28) else {
            return false
        }
        let width = Int(width32)
        let height = Int(height32)
        let stride = Int(stride32)
        guard width > 0, width <= 10_000,
              height > 0, height <= 10_000,
              stride == width * 3 || stride == width * 4 else {
            return false
        }
        let byteCount = stride * height
        let payloadStart = cursor + 40
        guard payloadStart + byteCount <= data.count else { return false }

        let payload = data.subdata(in: payloadStart..<(payloadStart + byteCount))
        var rgba = [UInt8](repeating: 0, count: width * height * 4)

        payload.withUnsafeBytes { buffer in
            guard let base = buffer.bindMemory(to: UInt8.self).baseAddress else { return }
            for row in 0..<height {
                let rowStart = row * stride
                for column in 0..<width {
                    let index = rowStart + column * (stride / width)
                    let blue = base[index]
                    let green = base[index + 1]
                    let red = base[index + 2]
                    var alpha = stride == width * 4 ? base[index + 3] : 255
                    if stride == width * 4, alpha == 0 {
                        alpha = 255
                    }
                    let output = (row * width + column) * 4
                    if stride == width * 4, alpha != 255 {
                        let alphaFactor = Int(alpha)
                        rgba[output] = UInt8(min(255, Int(red) * alphaFactor / 255 + (255 - alphaFactor)))
                        rgba[output + 1] = UInt8(min(255, Int(green) * alphaFactor / 255 + (255 - alphaFactor)))
                        rgba[output + 2] = UInt8(min(255, Int(blue) * alphaFactor / 255 + (255 - alphaFactor)))
                    } else {
                        rgba[output] = red
                        rgba[output + 1] = green
                        rgba[output + 2] = blue
                    }
                    rgba[output + 3] = 255
                }
            }
        }

        return writePNG(rgba: rgba, width: width, height: height, to: outPNG)
    }

    private static func writePNG(rgba: [UInt8], width: Int, height: Int, to url: URL) -> Bool {
        let data = Data(rgba)
        guard let provider = CGDataProvider(data: data as CFData),
              let image = CGImage(
                width: width,
                height: height,
                bitsPerComponent: 8,
                bitsPerPixel: 32,
                bytesPerRow: width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
                provider: provider,
                decode: nil,
                shouldInterpolate: false,
                intent: .defaultIntent
              ),
              let destination = CGImageDestinationCreateWithURL(
                url as CFURL,
                UTType.png.identifier as CFString,
                1,
                nil
              ) else {
            return false
        }
        CGImageDestinationAddImage(destination, image, nil)
        return CGImageDestinationFinalize(destination)
    }

    private static func readUInt16(_ data: Data, _ offset: Int) -> UInt16? {
        guard offset >= 0, offset + 2 <= data.count else { return nil }
        return data[offset..<(offset + 2)].withUnsafeBytes {
            UInt16(littleEndian: $0.loadUnaligned(as: UInt16.self))
        }
    }

    private static func readUInt32(_ data: Data, _ offset: Int) -> UInt32? {
        guard offset >= 0, offset + 4 <= data.count else { return nil }
        return data[offset..<(offset + 4)].withUnsafeBytes {
            UInt32(littleEndian: $0.loadUnaligned(as: UInt32.self))
        }
    }
}
