import CoreGraphics
import ImageIO
import XCTest
@testable import CP4AICore

final class EMFPlusExtractorTests: XCTestCase {
    private func append<T: FixedWidthInteger>(_ value: T, to data: inout Data) {
        var little = value.littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    private func makeEMF(width: UInt32, height: UInt32, stride: UInt32, payload: [UInt8]) -> Data {
        var data = Data()
        let subrecordSize = UInt32(40 + payload.count)
        append(UInt32(70), to: &data)
        append(UInt32(16 + subrecordSize), to: &data)
        append(UInt32(0x2B464D45), to: &data)
        append(UInt32(0), to: &data)
        append(UInt16(0x4008), to: &data)
        append(UInt16(0), to: &data)
        append(subrecordSize, to: &data)
        append(UInt32(payload.count), to: &data)
        append(UInt32(0), to: &data)
        append(UInt32(0), to: &data)
        append(width, to: &data)
        append(height, to: &data)
        append(stride, to: &data)
        append(UInt32(0), to: &data)
        append(UInt32(0), to: &data)
        data.append(contentsOf: payload)
        return data
    }

    func testExtractsOnePixelBitmap() throws {
        let directory = try TemporaryDirectory(prefix: "cp4ai_emf_test_")
        let emf = directory.url.appendingPathComponent("test.emf")
        let png = directory.url.appendingPathComponent("test.png")
        try makeEMF(width: 1, height: 1, stride: 4, payload: [0, 0, 255, 255]).write(to: emf)

        XCTAssertTrue(EMFPlusExtractor.extract(emf: emf, outPNG: png))
        XCTAssertTrue(FileManager.default.fileExists(atPath: png.path))
        guard let source = CGImageSourceCreateWithURL(png as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            return XCTFail("could not read extracted PNG")
        }
        XCTAssertEqual(image.width, 1)
        XCTAssertEqual(image.height, 1)
    }

    func testMixedAlphaFlattensTransparentPixelsToWhite() throws {
        let directory = try TemporaryDirectory(prefix: "cp4ai_emf_alpha_test_")
        let emf = directory.url.appendingPathComponent("alpha.emf")
        let png = directory.url.appendingPathComponent("alpha.png")
        // Pixel 1: red with alpha 0. Pixel 2: opaque green.
        let payload: [UInt8] = [0, 0, 255, 0, 0, 255, 0, 255]
        try makeEMF(width: 2, height: 1, stride: 8, payload: payload).write(to: emf)

        XCTAssertTrue(EMFPlusExtractor.extract(emf: emf, outPNG: png))
        guard let source = CGImageSourceCreateWithURL(png as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            return XCTFail("could not read extracted PNG")
        }

        var pixels = [UInt8](repeating: 0, count: 2 * 4)
        guard let context = CGContext(
            data: &pixels,
            width: 2,
            height: 1,
            bitsPerComponent: 8,
            bytesPerRow: 8,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
        ) else {
            return XCTFail("could not create context")
        }
        context.draw(image, in: CGRect(x: 0, y: 0, width: 2, height: 1))
        XCTAssertEqual(Array(pixels[0..<3]), [255, 255, 255])
        XCTAssertEqual(Array(pixels[4..<7]), [0, 255, 0])
    }
}
