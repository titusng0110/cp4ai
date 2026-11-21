import CoreGraphics
import ImageIO
import XCTest
@testable import CP4AICore

final class EMFPlusExtractorTests: XCTestCase {
    func testExtractsOnePixelBitmap() throws {
        let directory = try TemporaryDirectory(prefix: "cp4ai_emf_test_")
        let emf = directory.url.appendingPathComponent("test.emf")
        let png = directory.url.appendingPathComponent("test.png")

        var data = Data()
        func append<T: FixedWidthInteger>(_ value: T) {
            var little = value.littleEndian
            withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
        }

        // EMR_COMMENT header: type 70, size 60, comment id "EMF+".
        append(UInt32(70))
        append(UInt32(60))
        append(UInt32(0x2B464D45))
        append(UInt32(0))
        // EmfPlusBitmap subrecord: type, flags, size 44, data size 4.
        append(UInt16(0x4008))
        append(UInt16(0))
        append(UInt32(44))
        append(UInt32(4))
        append(UInt32(0))
        append(UInt32(0))
        // Width, height, stride.
        append(UInt32(1))
        append(UInt32(1))
        append(UInt32(4))
        // Reserved bytes before the pixel payload.
        append(UInt32(0))
        append(UInt32(0))
        // BGRA payload (red).
        data.append(contentsOf: [0, 0, 255, 255])
        try data.write(to: emf)

        XCTAssertTrue(EMFPlusExtractor.extract(emf: emf, outPNG: png))
        XCTAssertTrue(FileManager.default.fileExists(atPath: png.path))
        guard let source = CGImageSourceCreateWithURL(png as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            return XCTFail("could not read extracted PNG")
        }
        XCTAssertEqual(image.width, 1)
        XCTAssertEqual(image.height, 1)
    }
}
